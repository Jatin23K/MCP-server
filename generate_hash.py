import bcrypt
import getpass
from datetime import datetime

def generate_bcrypt_hash():
    """Generates and prints the bcrypt hash for a hardcoded password.

    WARNING: Hardcoding passwords in scripts is a security risk.
    This script is for demonstration or specific, controlled use cases only.
    """
    # !!! SECURITY RISK: Replace this with your password ONLY if you understand the risks !!!
    password = "#Jk2025Sy#"
    # bcrypt works with bytes, so encode the password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    # Decode the hash back to a string for printing
    print("\nYour bcrypt hash:")
    print(hashed.decode('utf-8'))

if __name__ == "__main__":
    generate_bcrypt_hash()
