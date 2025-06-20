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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status, BackgroundTasks, Path as FastAPIPath
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


@router.get(
    "/files",
    response_model=FileListResponse,
    summary="List files",
    description="List files with optional filtering and pagination."
)
async def list_files(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    prefix: Optional[str] = Query(
        None,
        description="Filter files by a path prefix (e.g., 'documents/')"
    ),
    extension: Optional[str] = Query(
        None,
        description="Filter files by file extension (e.g., 'txt', 'py'). Do not include the dot."
    ),
    tags: Optional[List[str]] = Query(
        None,
        description="Filter files by associated tags (comma-separated if multiple)"
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Number of files to skip for pagination"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of files to return"
    )
) -> FileListResponse:
    """
    List files in the system.

    - **prefix**: Filter by directory or path prefix.
    - **extension**: Filter by file extension (e.g., 'txt', 'json').
    - **tags**: Filter by associated tags.
    - **skip**: Number of files to skip for pagination.
    - **limit**: Maximum number of files to return.
    """
    try:
        files = await file_manager.list_files(
            prefix=prefix,
            extension=extension,
            tags=tags,
            skip=skip,
            limit=limit
        )
        total_files = await file_manager.count_files(
            prefix=prefix,
            extension=extension,
            tags=tags
        )
        return FileListResponse(
            success=True,
            message="Files listed successfully.",
            data=files,
            total=total_files,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.post("/files/upload", response_model=FileResponseModel, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    path: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    overwrite: bool = Form(False),
    file_manager: FileManager = Depends(get_file_manager_dependency),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Upload a file to the server.
    
    - **file**: The file to upload
    - **path**: Optional target path (including filename)
    - **metadata**: Optional JSON string with file metadata
    - **overwrite**: Whether to overwrite if file exists
    """
    try:
        # Parse metadata if provided
        file_metadata = None
        if metadata:
            try:
                file_metadata = json.loads(metadata)
                if not isinstance(file_metadata, dict):
                    raise ValueError("Metadata must be a JSON object")
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid metadata format. Must be a valid JSON object."
                )
        
        # Upload the file
        metadata = await file_manager.upload_file(
            file=file,
            target_filename=path,
            metadata=file_metadata,
            overwrite=overwrite
        )
        
        # Update context in background
        background_tasks.add_task(
            update_context_for_file,
            filename=metadata.filename,
            operation_type="upload"
        )
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "data": metadata.dict()
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except FileExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file"
        )


@router.get(
    "/files/download",
    summary="Download a file",
    description="Download a file by its path.",
    response_class=StreamingResponse # Use StreamingResponse for large files
)
async def download_file(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    file_path: str = Query(..., description="The full path of the file to download (e.g., 'documents/report.pdf')"),
    download: bool = Query(
        True,
        description="If true, forces download. If false, attempts to display in browser."
    )
):
    """
    Download a file.

    - **file_path**: The path of the file to download.
    - **download**: If true, forces download; otherwise, attempts to display in browser.
    """
    try:
        file_info = await file_manager.get_file_info(file_path)
        if not file_info:
            raise HTTPException(status_code=404, detail=f"File '{file_path}' not found.")

        headers = {
            "Content-Disposition": f"attachment; filename=\"{Path(file_path).name}\"" if download else "inline",
            "Content-Type": file_info.content_type or "application/octet-stream",
            "Content-Length": str(file_info.size)
        }

        return FileResponse(
            file_info.path,
            media_type=file_info.content_type or "application/octet-stream",
            filename=Path(file_path).name,
            content_disposition_type="attachment" if download else "inline"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found on disk.")
    except Exception as e:
        logger.error(f"Error downloading file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")

@router.get(
    "/files/debug-list-internal-filenames",
    response_model=FileListResponse,
    summary="Debug: List Internal Filenames",
    description="Returns a list of all internal filenames tracked by the FileManager for debugging purposes. Do not use in production."
)
async def debug_list_internal_filenames(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)]
) -> FileListResponse:
    """
    Debug endpoint to list all internal filenames.
    """
    try:
        filenames = await file_manager.debug_list_all_filenames()
        return FileListResponse(
            success=True,
            message="Internal filenames retrieved successfully.",
            data=filenames
        )
    except Exception as e:
        logger.error(f"Error in debug_list_internal_filenames: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve internal filenames: {str(e)}")

@router.get(
    "/files/info",
    response_model=FileResponseModel,
    summary="Get file information",
    description="Retrieve detailed information about a file by its path."
)
async def get_file_info(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    file_path: str = Query(..., description="The full path of the file to get info for.")
) -> FileResponseModel:
    """
    Get file information.

    - **file_path**: The path of the file to get information about.
    """
    try:
        file_info = await file_manager.get_file_info(file_path)
        if file_info:
            return FileResponseModel(
                success=True,
                message=f"File info for '{file_path}' retrieved successfully.",
                data=file_info
            )
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found.")
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get file info: {str(e)}")

@router.delete(
    "/files/{file_id}",
    response_model=StatusResponse,
    summary="Delete a file",
    description="Delete a file by its ID"
)
async def delete_file(
    file_id: str = FastAPIPath(..., description="The ID of the file to delete"),
    permanent: bool = Query(
        False,
        description="If true, permanently deletes the file. Otherwise, moves it to trash."
    ),
    file_manager: FileManager = Depends(get_file_manager_dependency),
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> StatusResponse:
    """
    Delete a file or move it to trash.
    
    - **file_id**: The unique identifier of the file
    - **permanent**: If true, permanently deletes the file (default: false)
    """
    try:
        # Get file metadata before deletion for background task
        try:
            file_metadata = await file_manager.get_file_metadata(file_id)
            file_path = file_metadata.path
        except FileNotFoundError:
            file_path = None

        # Delete the file
        if permanent:
            await file_manager.delete_file(file_id)
            message = f"File '{file_id}' permanently deleted"
        else:
            await file_manager.move_to_trash(file_id)
            message = f"File '{file_id}' moved to trash"

        # Update context in background if we have the file path
        if file_path:
            background_tasks.add_task(
                update_context_for_file,
                filename=file_path,
                operation_type="delete"
            )

        return StatusResponse(
            success=True,
            message=message,
            data={"file_id": file_id}
        )

    except FileNotFoundError as e:
        logger.warning(f"File not found: {file_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_id}"
        )
    except PermissionError as e:
        logger.error(f"Permission denied when deleting file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete the file"
        )
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}"
        )

@router.post(
    "/files/scan-and-register",
    response_model=StatusResponse,
    summary="Scan and register existing files",
    description="Scans the file storage directory for existing files and registers them with the system."
)
async def scan_and_register_files(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
) -> StatusResponse:
    """
    Scan for existing files and register them.
    """
    try:
        await file_manager.scan_and_register_existing_files()
        return StatusResponse(
            success=True,
            message="File system scanned and existing files registered successfully."
        )
    except Exception as e:
        logger.error(f"Error scanning and registering files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to scan and register files: {str(e)}")

@router.put(
    "/files/metadata",
    response_model=FileResponseModel,
    summary="Update file metadata",
    description="Update metadata for a specific file by its path."
)
async def update_file_metadata(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    background_tasks: BackgroundTasks,
    file_path: str = Query(..., description="The full path of the file to update metadata for."),
    metadata: str = Form(..., description="JSON string with the metadata to update. Existing keys will be overwritten.")
) -> FileResponseModel:
    """
    Update metadata for a file.

    - **file_path**: The path of the file to update metadata for.
    - **metadata**: JSON string with the metadata to update.
    """
    try:
        new_metadata = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for metadata.")

    try:
        updated_file_info = await file_manager.update_file_metadata(file_path, new_metadata)
        if updated_file_info:
            background_tasks.add_task(update_context_for_file, file_path, "update_metadata")
            return FileResponseModel(
                success=True,
                message=f"Metadata for '{file_path}' updated successfully.",
                data=updated_file_info
            )
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found.")
    except Exception as e:
        logger.error(f"Error updating metadata for file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update metadata: {str(e)}")

@router.get(
    "/files/versions",
    response_model=FileVersionListResponse,
    summary="List file versions",
    description="List all versions of a specific file."
)
async def list_file_versions(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    file_path: str = Query(..., description="The full path of the file to list versions for.")
) -> FileVersionListResponse:
    """
    List all versions of a file.

    - **file_path**: The path of the file to list versions for.
    """
    try:
        versions = await file_manager.list_file_versions(file_path)
        if versions is not None:
            return FileVersionListResponse(
                success=True,
                message=f"Versions for '{file_path}' retrieved successfully.",
                data=versions,
                total=len(versions)
            )
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found or has no versions.")
    except Exception as e:
        logger.error(f"Error listing versions for file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list file versions: {str(e)}")

@router.get(
    "/files/versions/download",
    summary="Download a specific file version",
    description="Download a specific version of a file by its path and version ID.",
    response_class=StreamingResponse
)
async def download_file_version(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    file_path: str = Query(..., description="The full path of the file."),
    version_id: str = Query(..., description="The version ID of the file to download."),
    download: bool = Query(
        True,
        description="If true, forces download. If false, attempts to display in browser."
    )
):
    """
    Download a specific version of a file.

    - **file_path**: The path of the file.
    - **version_id**: The ID of the version to download.
    - **download**: If true, forces download; otherwise, attempts to display in browser.
    """
    try:
        version_info = await file_manager.get_file_version_info(file_path, version_id)
        if not version_info:
            raise HTTPException(status_code=404, detail=f"Version '{version_id}' for file '{file_path}' not found.")

        version_local_path = file_manager.get_version_local_path(file_path, version_id)

        headers = {
            "Content-Disposition": f"attachment; filename=\"{Path(file_path).name}_v{version_id}\"" if download else "inline",
            "Content-Type": version_info.content_type or "application/octet-stream",
            "Content-Length": str(version_info.size)
        }

        return FileResponse(
            version_local_path,
            media_type=version_info.content_type or "application/octet-stream",
            filename=f"{Path(file_path).name}_v{version_id}",
            content_disposition_type="attachment" if download else "inline"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Version file '{version_id}' for '{file_path}' not found on disk.")
    except Exception as e:
        logger.error(f"Error downloading version {version_id} for file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download file version: {str(e)}")

@router.post(
    "/files/upload-directory",
    response_model=FileResponseModel,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a directory",
    description="Upload multiple files while maintaining directory structure."
)
async def upload_directory(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    path: Optional[str] = Form(None),
    overwrite: bool = Form(False),
    metadata: Optional[str] = Form(None)
) -> FileResponseModel:
    """
    Upload multiple files while maintaining directory structure.

    - **files**: List of files to upload
    - **path**: Optional base path where to store the files
    - **overwrite**: Whether to overwrite if files exist (default: False)
    - **metadata**: Optional JSON string with file metadata
    """
    uploaded_files = []
    try:
        base_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for metadata.")

    for file in files:
        if file.size and file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{file.filename}' size exceeds the maximum limit of {MAX_FILE_SIZE / (1024 * 1024):.0f} MB."
            )

        file_extension = Path(file.filename).suffix.lower() if file.filename else ""
        if file_extension and file_extension not in ALLOWED_FILE_EXTENSIONS:
            logger.warning(f"Attempted to upload file with disallowed extension: {file_extension}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{file_extension}' for '{file.filename}' is not allowed."
            )

        try:
            # Construct the logical file path
            logical_file_path = Path(path or "") / file.filename

            # Merge base metadata with any file-specific metadata if needed
            file_metadata = base_metadata.copy() # Start with base metadata

            # Save the file
            saved_file_info = await file_manager.upload_file(
                file=file,
                metadata=file_metadata,
                overwrite=overwrite,
                target_filename=logical_file_path.as_posix()
            )

            uploaded_files.append(saved_file_info)

            # Update context if this is a parse request
            parseable_extensions = ('.txt', '.md', '.csv', '.json')
            if saved_file_info.filename.lower().endswith(parseable_extensions):
                background_tasks.add_task(
                    update_context_for_file,
                    saved_file_info.filename,
                    "upload"
                )

        except FileExistsError:
            raise HTTPException(status_code=409, detail=f"File '{logical_file_path}' already exists. Use overwrite=true to replace.")
        except Exception as e:
            logger.error(f"Error processing file {file.filename} in directory upload: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to upload file '{file.filename}': {str(e)}")

    return FileResponseModel(
        success=True,
        message=f"Successfully uploaded {len(uploaded_files)} files.",
        data=[f.model_dump() for f in uploaded_files] # Ensure data is serializable
    )

@router.post(
    "/files/parse",
    response_model=StatusResponse,
    summary="Parse file content",
    description="Parses the content of a specified file and extracts information."
)
async def parse_file(
    file_manager: Annotated[FileManager, Depends(get_file_manager_dependency)],
    context_manager: Annotated[ContextManager, Depends(get_context_manager_dependency)],
    file_path: str = Query(..., description="The full path of the file to parse."),
    parser_name: Optional[str] = Query(
        "default",
        description="The name of the parser to use (e.g., 'markdown_parser', 'json_parser'). 'default' will use an intelligent guess."
    )
) -> StatusResponse:
    """
    Parse the content of a file.

    - **file_path**: The path of the file to parse.
    - **parser_name**: Optional name of the parser to use.
    """
    try:
        success, message = await file_manager.parse_file_content(file_path, parser_name)
        if success:
            return StatusResponse(
                success=True,
                message=message
            )
        raise HTTPException(status_code=500, detail=message)
    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions directly
    except Exception as e:
        logger.error(f"Error parsing file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")