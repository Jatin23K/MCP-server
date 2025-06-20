import logging
import json
import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime

logger = logging.getLogger(__name__)

# Define the path for the user data JSON file
USERS_FILE = os.getenv("USERS_FILE_PATH", "data/users/users.json")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable must be set")

# Token configuration
TOKEN_EXPIRATION_MINUTES = int(os.getenv("TOKEN_EXPIRATION_MINUTES", "60"))  # Default to 1 hour

class User(BaseModel):
    """Basic User model."""
    username: str
    hashed_password: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    roles: List[str] = []
    disabled: bool = False
    created_at: Optional[str] = None
    last_login: Optional[str] = None

class UserManager:
    """Manages user data, including persistence to a JSON file."""
    def __init__(self, pwd_context: CryptContext):
        logger.info("Initializing User Manager")
        self.pwd_context = pwd_context
        self._users: Dict[str, User] = {}
        self._load_users()

    def _load_users(self):
        """Loads users from the JSON file."""
        user_data_path = USERS_FILE
        if os.path.exists(user_data_path):
            try:
                with open(user_data_path, "r") as f:
                    users_data = json.load(f)
                    for user_dict in users_data:
                        if "hashed_password" in user_dict:
                            self._users[user_dict["username"]] = User(**user_dict)
                logger.info(f"Loaded {len(self._users)} users from {USERS_FILE}")
            except Exception as e:
                logger.error(f"Error loading users from {USERS_FILE}: {e}")
        else:
            logger.info(f"{USERS_FILE} not found, starting with no users.")
            self._create_default_users()

    def _save_users(self):
        """Saves current users to the JSON file."""
        user_data_path = USERS_FILE
        try:
            os.makedirs(os.path.dirname(user_data_path), exist_ok=True)
            with open(user_data_path, "w") as f:
                json.dump([user.model_dump() for user in self._users.values()], f, indent=4)
            logger.info(f"Saved {len(self._users)} users to {USERS_FILE}")
        except Exception as e:
            logger.error(f"Error saving users to {USERS_FILE}: {e}")

    def _create_default_users(self):
        """Creates initial default users if the user file doesn't exist."""
        logger.info("Creating default users...")
        self.create_user_sync("Jatin23K", "#JK2025sy#", email="jatin@example.com", full_name="Jatin", roles=["admin"])
        self.create_user_sync("coder1", "securepass", email="coder1@example.com", full_name="Coder One", roles=["user"])
        self._save_users()

    def create_user_sync(self, username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None, roles: Optional[List[str]] = None) -> User:
        """Synchronously create a new user and hash password (for initial setup)."""
        if username in self._users:
            logger.warning(f"Attempted to create user '{username}' which already exists.")
            return self._users[username]

        hashed_password = self.pwd_context.hash(password)
        now = datetime.utcnow().isoformat()
        new_user = User(username=username, hashed_password=hashed_password, email=email, full_name=full_name, roles=roles or [], created_at=now, last_login=None)
        self._users[username] = new_user
        logger.info(f"User '{username}' created (sync).")
        return new_user

    async def create_user(self, username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None, roles: Optional[List[str]] = None) -> User:
        """Asynchronously create a new user, hash password, and save."""
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")

        hashed_password = self.pwd_context.hash(password)
        now = datetime.utcnow().isoformat()
        new_user = User(username=username, hashed_password=hashed_password, email=email, full_name=full_name, roles=roles or [], created_at=now, last_login=None)
        self._users[username] = new_user
        self._save_users()
        logger.info(f"User '{username}' created.")
        return new_user

    async def get_user(self, username: str) -> Optional[User]:
        """Asynchronously get a user by username."""
        return self._users.get(username)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password."""
        return self.pwd_context.verify(plain_password, hashed_password)

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user with username and password."""
        logger.debug(f"Attempting to authenticate user: {username}")
        user = await self.get_user(username)
        if not user:
            logger.warning(f"Authentication failed: User '{username}' not found.")
            return None
        
        logger.debug(f"User '{username}' found. Verifying password...")
        if not self.verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: Incorrect password for user '{username}'.")
            return None
        
        logger.info(f"Authentication successful for user: {username}")
        return user

    def create_access_token(self, data: dict) -> str:
        """Create a JWT access token."""
        from jose import jwt
        from datetime import datetime, timedelta

        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRATION_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify a JWT token."""
        from jose import jwt, JWTError

        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            return payload
        except JWTError:
            return None

    def has_permission(self, username: str, action: str) -> bool:
        """
        Check if the user has permission to perform the given action.
        - 'admin' role: all permissions
        - 'user' role: only 'read'
        """
        user = self._users.get(username)
        if not user or user.disabled:
            return False
        if "admin" in user.roles:
            return True
        if "user" in user.roles and action == "read":
            return True
        return False

    def list_users(self) -> list:
        """Return a list of all users."""
        return list(self._users.values())

    async def update_user(self, username: str, email: Optional[str] = None, full_name: Optional[str] = None, roles: Optional[List[str]] = None, disabled: Optional[bool] = None) -> Optional[User]:
        """Update an existing user's information."""
        user = await self.get_user(username)
        if user is None:
            logger.warning(f"Attempted to update non-existent user: {username}")
            return None

        # Update fields if provided
        if email is not None:
            user.email = email
        if full_name is not None:
            user.full_name = full_name
        if roles is not None: # Allow empty list [] for roles
            user.roles = roles
        if disabled is not None:
            user.disabled = disabled

        # Note: Password updates should likely be handled by a separate method for security

        self._save_users()
        logger.info(f"User '{username}' updated.")
        return user

    async def delete_user(self, username: str) -> bool:
        """Delete a user by username."""
        if username in self._users:
            del self._users[username]
            self._save_users()
            logger.info(f"User '{username}' deleted.")
            return True
        logger.warning(f"Attempted to delete non-existent user: {username}")
        return False

# Singleton instance
# Initialize the UserManager directly when the module is imported
from passlib.context import CryptContext
pwd_context_global = CryptContext(schemes=["bcrypt"], deprecated="auto")
user_manager: Optional[UserManager] = UserManager(pwd_context_global)

# Dependency to get the UserManager instance
async def get_user_manager() -> UserManager:
    """Dependency for FastAPI to get the user manager instance."""
    if user_manager is None:
        # This case should ideally not be reached with direct initialization
        logger.error("UserManager accessed before initialization!")
        raise RuntimeError("User manager not initialized")
    logger.debug(f"get_user_manager returning type: {type(user_manager)}")
    return user_manager 