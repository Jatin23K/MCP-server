"""File Management Routes for FastMCP Server.

This module defines the API endpoints for file operations, including uploading,
downloading, listing, deleting, and managing file metadata and versions.
It integrates with the FileManager for core file system interactions.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, List, Optional, Any, Dict, Union
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import ValidationError

from app.core.file_manager import FileManager
from app.core.context_manager import ContextManager
from app.models.pydantic_models import (
    FileMetadata, FileInfo, FileResponseModel, StatusResponse,
    FileListResponse, FileVersionInfo, FileVersionListResponse
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize APIRouter
router = APIRouter(
    prefix="/api/v1",
    tags=["File Management"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"}
    }
)

# Constants
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
ALLOWED_FILE_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".xml", ".yaml", ".yml",
    ".log", ".py", ".js", ".ts", ".html", ".css", ".go", ".java",
    ".cpp", ".c", ".h", ".sh", ".bash", ".env", ".gitignore", ".sql",
    ".dockerfile", ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar",
    ".gz", ".bz2", ".xz", ".rar", ".7z", ".mp3", ".wav", ".flac",
    ".mp4", ".avi", ".mkv", ".mov", ".jpg", ".jpeg", ".png", ".gif",
    ".bmp", ".svg", ".ico", ".vue", ".jsx", ".tsx", ".toml", ".ini"
}

# Dependency to get the FileManager instance
async def get_file_manager_dependency() -> FileManager:
    """Get the global file manager instance."""
    from app.main import mcp_file_manager
    if not mcp_file_manager or not hasattr(mcp_file_manager, '_is_running') or not mcp_file_manager._is_running:
        # Initialize if not running (e.g., during testing or direct script execution)
        if mcp_file_manager:
            await mcp_file_manager.initialize()
        else:
            raise HTTPException(status_code=500, detail="File Manager not initialized.")
    return mcp_file_manager

# Dependency to get the ContextManager instance (if needed for file routes)
async def get_context_manager_dependency() -> ContextManager:
    """Get the global context manager instance."""
    from app.main import mcp_context_manager
    if not mcp_context_manager or not hasattr(mcp_context_manager, '_is_running') or not mcp_context_manager._is_running:
        # Initialize if not running (e.g., during testing or direct script execution)
        if mcp_context_manager:
            await mcp_context_manager.initialize()
        else:
            raise HTTPException(status_code=500, detail="Context Manager not initialized.")
    return mcp_context_manager

async def update_context_for_file(
    filename: str,
    operation_type: str, # "upload", "delete", "update_metadata", "new_version"
    context_manager: ContextManager = Depends(get_context_manager_dependency)
):
    """
    Helper function to update context based on file actions.
    This function will be run in the background.
    """
    context_key = f"file_activity:{filename}"
    value = {"filename": filename, "operation": operation_type, "timestamp": datetime.now().isoformat()}
    await context_manager.set_context(key=context_key, value=value)
    logger.info(f"Context updated for file '{filename}' with operation '{operation_type}'.")

# ... (rest of the file remains the same)