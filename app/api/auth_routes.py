"""
Authentication Routes for FastMCP Server.

This module provides API endpoints for:
- User registration
- User authentication
- User management
- Role-based access control
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional, Annotated
from pydantic import BaseModel, EmailStr
import logging

from app.core.user_manager import User, get_user_manager, UserManager
from app.core.context_manager import mcp_context_manager
from app.models.pydantic_models import ContextItem, ContextBulkOperation, ContextQuery, SearchResults, SearchResultItem, RegisterRequest, UserPublic

router = APIRouter()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/mcp/api/v1/token")

class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Token data model."""
    username: Optional[str] = None

class UserCreate(BaseModel):
    """User creation model."""
    username: str
    password: str
    email: EmailStr
    full_name: str
    roles: Optional[List[str]] = None

class UserUpdate(BaseModel):
    """User update model."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    roles: Optional[List[str]] = None
    disabled: Optional[bool] = None

class UserResponse(BaseModel):
    """User response model."""
    username: str
    email: str
    full_name: str
    roles: List[str]
    disabled: bool
    created_at: str
    last_login: Optional[str] = None

async def get_current_user(user_manager: Annotated[UserManager, Depends(get_user_manager)], token: str = Depends(oauth2_scheme)) -> User:
    """Get current user from token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = user_manager.verify_token(token)
    if payload is None:
        raise credentials_exception
        
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    user = await user_manager.get_user(username)
    if user is None:
        raise credentials_exception
        
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

@router.post("/token", response_model=Token)
async def login_for_access_token(user_manager: Annotated[UserManager, Depends(get_user_manager)], form_data: OAuth2PasswordRequestForm = Depends()):
    """Login to get access token."""
    try:
        user = await user_manager.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        access_token = user_manager.create_access_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during authentication"
        )

@router.post("/users", response_model=UserResponse)
async def create_user(user_manager: Annotated[UserManager, Depends(get_user_manager)], user: UserCreate, current_user: User = Depends(get_current_active_user)):
    """Create a new user."""
    if not user_manager.has_permission(current_user.username, "write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
        
    try:
        new_user = await user_manager.create_user(
            username=user.username,
            password=user.password,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles
        )
        return UserResponse(**new_user.model_dump())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/users/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return UserResponse(**current_user.model_dump())

@router.get("/users", response_model=List[UserResponse])
async def list_users(user_manager: Annotated[UserManager, Depends(get_user_manager)], current_user: User = Depends(get_current_active_user)):
    """List all users.""" # Check dependencies and types
    if not user_manager.has_permission(current_user.username, "read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
        
    return [UserResponse(**user.model_dump()) for user in user_manager.list_users()]

@router.put("/users/{username}", response_model=UserResponse)
async def update_user(
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    username: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update user information."""
    if not user_manager.has_permission(current_user.username, "write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
        
    updated_user = await user_manager.update_user(
        username=username,
        email=user_update.email,
        full_name=user_update.full_name,
        roles=user_update.roles,
        disabled=user_update.disabled
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    return UserResponse(**updated_user.model_dump())

@router.delete("/users/{username}")
async def delete_user(
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    username: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete a user."""
    if not user_manager.has_permission(current_user.username, "delete"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
        
    if not await user_manager.delete_user(username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    return {"message": "User deleted successfully"}

@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Register a new user with username, password, and optional details."
)
async def register_user(user_manager: Annotated[UserManager, Depends(get_user_manager)], user_data: RegisterRequest):
    """
    Register a new user.

    - **username**: Unique username
    - **password**: User password
    - **confirm_password**: Confirm password (must match password)
    - **roles**: List of roles (defaults to ["user"])
    - **email**: Optional email address
    - **full_name**: Optional full name
    """
    try:
        # Check if user already exists
        existing_user = await user_manager.get_user(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        # Create the user using the UserManager (password hashing is handled internally)
        new_user = await user_manager.create_user(
            username=user_data.username,
            password=user_data.password, # Pass plain password for hashing
            email=user_data.email,
            full_name=user_data.full_name,
            roles=user_data.roles
        )

        # Return the public user model
        return UserPublic(**new_user.model_dump())

    except ValueError as e:
        logger.error(f"Validation error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise # Re-raise explicit HTTPExceptions
    except Exception as e:
        logger.exception(f"Unexpected error during registration for user {user_data.username}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration"
        ) 