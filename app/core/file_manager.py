"""
File Manager for FastMCP Server.

This module provides a robust file management system that supports:
- File upload, download, and metadata management
- File versioning and history
- File system monitoring
- Asynchronous file operations
- Integration with context manager
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union, AsyncGenerator

import aiofiles
import aiofiles.os
import aiofiles.os as aios
from fastapi import UploadFile, HTTPException
from pydantic import BaseModel, Field, validator

try:
    import magic  # python-magic for content type detection
except ImportError:
    magic = None
    logger = logging.getLogger(__name__)
    logger.warning("python-magic not installed. File content type detection will be limited.")

from app.models.pydantic_models import Event, EventType, FileMetadata, FileInfo

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB max file size
ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'json', 'yaml', 'yml',
    'xlsx', 'xls', 'xlsm', 'xlsb',  # Excel formats
    'doc', 'docx',  # Word formats
    'ppt', 'pptx',  # PowerPoint formats
    'zip', 'rar',   # Archive formats
    'py', 'js', 'html', 'css', 'md'  # Code and markup formats
}

class FileManager:
    """
    Manages file storage, retrieval, and versioning.
    
    Features:
    - Async file operations
    - File versioning
    - Metadata management
    - File system monitoring
    - Integration with context manager
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        storage_root: str = "data/files",
        max_file_size: int = MAX_FILE_SIZE,
        allowed_extensions: Set[str] = None,
        context_manager: Optional["ContextManager"] = None
    ):
        """
        Initialize the File Manager.
        
        Args:
            storage_root: Base directory for file storage
            max_file_size: Maximum allowed file size in bytes
            allowed_extensions: Set of allowed file extensions
            context_manager: Optional ContextManager instance for event publishing
        """
        if not self._initialized:
            self.storage_root = Path(storage_root)
            self.max_file_size = max_file_size
            self.allowed_extensions = allowed_extensions or ALLOWED_EXTENSIONS
            self.context_manager = context_manager
            self._file_locks: Dict[str, asyncio.Lock] = {}
            self._setup_directories()
            self._initialized = True
            logger.info(f"FileManager initialized with storage root: {self.storage_root}")
            
    def _setup_directories(self):
        """Ensure required directories exist."""
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
            (self.storage_root / "tmp").mkdir(exist_ok=True)
            (self.storage_root / "versions").mkdir(exist_ok=True)
            (self.storage_root / "metadata").mkdir(exist_ok=True)
            logger.debug("FileManager directories set up successfully")
        except Exception as e:
            logger.error(f"Failed to set up FileManager directories: {e}")
            raise
            
    def _get_file_path(self, file_id: str, version: int = None) -> Path:
        """Get the filesystem path for a file ID and optional version."""
        if version is not None:
            return self.storage_root / "versions" / file_id / f"v{version}"
        return self.storage_root / file_id
        
    def _get_metadata_path(self, file_id: str, version: int = None) -> Path:
        """Get the path to a file's metadata."""
        if version:
            return self.storage_root / "metadata" / f"{file_id}_v{version}.json"
        return self.storage_root / "metadata" / f"{file_id}.json"
        
    def _validate_extension(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.allowed_extensions
        
    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
        
    async def file_exists(self, file_path: Union[str, Path]) -> bool:
        """Check if a file exists asynchronously at the given relative path."""
        if isinstance(file_path, str):
            file_path = Path(file_path)
        absolute_path = self.storage_root / file_path
        return await aios.path.exists(absolute_path)
        
    async def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish a file event to the context manager."""
        logger.info(f"Attempting to publish file event: {event_type} with data: {data}")
        if not self.context_manager:
            logger.warning("Context manager not available, skipping event publishing.")
            return
            
        try:
            event = Event(
                event_type=EventType.FILE_CHANGE,
                source="file_manager",
                data={
                    "event": event_type,
                    "timestamp": time.time(),
                    **data
                },
                correlation_id=str(uuid.uuid4())
            )
            logger.debug(f"Created event object: {event.model_dump_json()}")
            await self.context_manager.publish_event(event)
            logger.info(f"Successfully published file event: {event_type}")
        except Exception as e:
            logger.error(f"Error publishing file event {event_type}: {e}", exc_info=True)
        
    async def upload_file(
        self,
        file: UploadFile,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        overwrite: bool = False,
        target_filename: Optional[str] = None
    ) -> FileMetadata:
        """
        Upload a new file or new version of an existing file.
        
        Args:
            file: FastAPI UploadFile object
            metadata: Optional file metadata
            tags: Optional list of tags
            overwrite: Whether to overwrite existing file
            target_filename: The desired logical path for the file, including directories (e.g., "documents/report.pdf")
            
        Returns:
            FileMetadata for the uploaded file
            
        Raises:
            ValueError: For invalid file or metadata
            IOError: For file system errors
        """
        # Determine the effective filename for storage, normalizing it to POSIX path
        effective_filename = Path(target_filename or file.filename).as_posix()

        # Validate input
        if not effective_filename:
            raise ValueError("No filename provided or derived")
            
        if not self._validate_extension(effective_filename):
            raise ValueError(f"File type not allowed. Allowed types: {', '.join(self.allowed_extensions)}")
            
        # Generate file ID
        file_id = str(uuid.uuid4())
        temp_path = self.storage_root / "tmp" / f"upload_{file_id}"
        
        try:
            # Save file to temp location
            file_size = 0
            async with aiofiles.open(temp_path, "wb") as f:
                while content := await file.read(8192):
                    file_size += len(content)
                    if file_size > self.max_file_size:
                        raise ValueError(f"File size exceeds maximum allowed size of {self.max_file_size} bytes")
                    await f.write(content)
                    
            # Calculate checksum
            checksum = await self._calculate_checksum(temp_path)
            
            # Check for existing file with same content
            existing_file = await self._find_file_by_checksum(checksum)
            if existing_file and not overwrite:
                await aios.remove(temp_path)
                return existing_file
                
            # Check for existing file with same name (using effective_filename for lookup)
            existing_file_by_name = await self.get_file_metadata_by_path(effective_filename)
            
            if existing_file_by_name and not overwrite:
                # Get next version number
                versions = await self.get_file_versions(existing_file_by_name.file_id)
                next_version = max([v.version for v in versions], default=0) + 1
                
                # Move to version location
                version_path = self._get_file_path(existing_file_by_name.file_id, next_version)
                version_path.parent.mkdir(parents=True, exist_ok=True)
                await aios.rename(temp_path, version_path)
                
                # Create metadata for new version
                file_metadata = FileMetadata(
                    file_id=existing_file_by_name.file_id,
                    filename=effective_filename, # Use the normalized effective_filename
                    content_type=file.content_type or "application/octet-stream",
                    size=file_size,
                    checksum=checksum,
                    metadata=metadata or {},
                    tags=tags or [],
                    created_at=time.time(),
                    updated_at=time.time(),
                    version=next_version
                )
                
                # Save metadata
                await self._save_metadata(file_metadata)
                
                # Publish event
                await self._publish_event("file_version_created", {
                    "file_id": existing_file_by_name.file_id,
                    "filename": effective_filename,
                    "version": next_version,
                    "size": file_size
                })
                
                return file_metadata
                
            # Move to final location for new file
            final_path = self._get_file_path(file_id)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            await aios.rename(temp_path, final_path)
            
            # Create metadata for new file
            file_metadata = FileMetadata(
                file_id=file_id,
                filename=effective_filename, # Use the normalized effective_filename
                content_type=file.content_type or "application/octet-stream",
                size=file_size,
                checksum=checksum,
                metadata=metadata or {},
                tags=tags or [],
                created_at=time.time(),
                updated_at=time.time(),
                version=1
            )
            
            # Save metadata
            await self._save_metadata(file_metadata)
            
            # Publish event
            await self._publish_event("file_created", {
                "file_id": file_id,
                "filename": effective_filename,
                "size": file_size
            })
            
            return file_metadata
            
        except Exception as e:
            # Clean up on error
            if temp_path.exists():
                await aios.remove(temp_path)
            raise
            
    async def download_file(self, file_id: str, version: int = None) -> Tuple[Path, FileMetadata]:
        """
        Get a file for download.
        
        Args:
            file_id: ID of the file to download
            version: Optional version number (defaults to latest)
            
        Returns:
            Tuple of (file_path, metadata)
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        metadata = await self.get_file_metadata(file_id, version)
        file_path = self._get_file_path(file_id, metadata.version if version is not None else None)
        
        if not await self.file_exists(file_path):
            raise FileNotFoundError(f"File {file_id} not found")
            
        return file_path, metadata
        
    async def get_file_metadata(self, file_id: str, version: int = None) -> FileMetadata:
        """
        Get metadata for a file.
        
        Args:
            file_id: ID of the file
            version: Optional version number (defaults to latest)
            
        Returns:
            FileMetadata object
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        metadata_path = self._get_metadata_path(file_id, version)
        
        logger.info(f"Attempting to retrieve metadata from: {metadata_path}")

        if not await aios.path.exists(metadata_path):
            raise FileNotFoundError(f"Metadata for file {file_id} not found")
            
        async with aiofiles.open(metadata_path, "r") as f:
            content = await f.read()
            
        return FileMetadata.parse_raw(content)
        
    async def list_files(
        self,
        prefix: Optional[str] = None,
        extension: Optional[str] = None,
        tags: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[FileMetadata]:
        """
        List all files with optional filtering and pagination.
        
        Args:
            prefix: Filter files by path prefix.
            extension: Filter files by their extension (e.g., "txt", "pdf").
            tags: Filter files by associated tags.
            skip: Number of items to skip for pagination.
            limit: Maximum number of items to return.
            
        Returns:
            A list of FileMetadata objects.
        """
        logger.info(f"Listing files with prefix='{prefix}', extension='{extension}', tags='{tags}', skip={skip}, limit={limit}")
        all_metadata_files = []
        try:
            async for metadata_path in self._iter_metadata_files():
                try:
                    async with aiofiles.open(metadata_path, 'r') as f:
                        content = await f.read()
                    metadata = FileMetadata.parse_raw(content)
                    if not metadata.is_deleted:
                        all_metadata_files.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to read or parse metadata file {metadata_path}: {e}")

            # Apply filters
            filtered_files = []
            for metadata in all_metadata_files:
                match = True
                if prefix:
                    normalized_prefix = prefix.replace('\\', '/').lower()
                    normalized_filename = metadata.filename.replace('\\', '/').lower()
                    if not normalized_filename.startswith(normalized_prefix):
                        match = False
                if extension and not metadata.filename.lower().endswith(f".{extension.lower()}"):
                    match = False
                if tags:
                    if not all(tag in metadata.tags for tag in tags):
                        match = False
                if match:
                    filtered_files.append(metadata)

            # Sort by last_modified (newest first)
            filtered_files.sort(key=lambda x: x.updated_at, reverse=True)
                
        # Apply pagination
            paginated_files = filtered_files[skip : skip + limit]

            logger.info(f"Successfully listed {len(paginated_files)} files (total filtered: {len(filtered_files)})")
            return paginated_files
        except Exception as e:
            logger.error(f"Error in list_files: {e}", exc_info=True)
            raise IOError(f"Failed to list files: {e}")

    async def count_files(
        self,
        prefix: Optional[str] = None,
        extension: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> int:
        """
        Count files matching optional filters.

        Args:
            prefix: Filter files by path prefix.
            extension: Filter files by their extension (e.g., "txt", "pdf").
            tags: Filter files by associated tags.

        Returns:
            The total number of matching files.
        """
        logger.info(f"Counting files with prefix='{prefix}', extension='{extension}', tags='{tags}'")
        count = 0
        try:
            async for metadata_path in self._iter_metadata_files():
                try:
                    async with aiofiles.open(metadata_path, 'r') as f:
                        content = await f.read()
                    metadata = FileMetadata.parse_raw(content)
                    if not metadata.is_deleted:
                        match = True
                        if prefix and not metadata.filename.startswith(prefix):
                            match = False
                        if extension and not metadata.filename.lower().endswith(f".{extension.lower()}"):
                            match = False
                        if tags:
                            if not all(tag in metadata.tags for tag in tags):
                                match = False
                        if match:
                            count += 1
                except Exception as e:
                    logger.warning(f"Failed to read or parse metadata file {metadata_path}: {e}")
            logger.info(f"Successfully counted {count} files.")
            return count
        except Exception as e:
            logger.error(f"Error in count_files: {e}", exc_info=True)
            raise IOError(f"Failed to count files: {e}")
        
    async def delete_file(self, file_id: str, permanent: bool = False) -> bool:
        """
        Delete a file or mark it as deleted.
        
        Args:
            file_id: ID of the file to delete
            permanent: If True, permanently delete the file
            
        Returns:
            bool: True if successful
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        try:
            metadata = await self.get_file_metadata(file_id)
            
            if permanent:
                # Remove file and metadata
                file_path = self._get_file_path(file_id)
                if file_path.exists():
                    await aios.remove(file_path)
                    
                # Remove all versions
                versions_dir = self.storage_root / "versions" / file_id
                if versions_dir.exists():
                    await aios.rmtree(versions_dir)
                    
                # Remove metadata
                metadata_path = self._get_metadata_path(file_id)
                if metadata_path.exists():
                    await aios.remove(metadata_path)
                    
                await self._publish_event("file_deleted_permanently", {
                    "file_id": file_id,
                    "filename": metadata.filename
                })
            else:
                # Mark as deleted
                metadata.is_deleted = True
                metadata.updated_at = time.time()
                await self._save_metadata(metadata)
                
                await self._publish_event("file_marked_deleted", {
                    "file_id": file_id,
                    "filename": metadata.filename
                })
                
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            raise
            
    async def _save_metadata(self, metadata: FileMetadata) -> None:
        """Save file metadata to disk.
        
        Args:
            metadata: FileMetadata object to save
        """
        try:
            # Create parent directories if they don't exist
            metadata_dir = self.storage_root / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            
            # Save metadata to file
            metadata_path = self._get_metadata_path(metadata.file_id, metadata.version)
            async with aiofiles.open(metadata_path, 'w') as f:
                await f.write(metadata.json(indent=2))
                
        except Exception as e:
            logger.error(f"Error saving metadata for {metadata.file_id}: {str(e)}")
            raise

    async def update_metadata(self, file_id: str, metadata_update: Dict[str, Any]) -> FileMetadata:
        """Update metadata for a file.
        
        Args:
            file_id: ID of the file to update
            metadata_update: Dictionary of fields to update
            
        Returns:
            Updated FileMetadata object
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If metadata_update is not a dictionary
        """
        if not isinstance(metadata_update, dict):
            raise ValueError("metadata_update must be a dictionary")
            
        # Get existing metadata
        metadata = await self.get_file_metadata(file_id)
        
        # Update fields
        update_data = metadata.dict()
        for key, value in metadata_update.items():
            if key in update_data and not key.startswith('_'):
                update_data[key] = value
        
        # Update timestamps
        update_data['updated_at'] = datetime.utcnow()
        
        # Create new metadata object
        updated_metadata = FileMetadata(**update_data)
        
        # Save updated metadata
        await self._save_metadata(updated_metadata)
        
        # Publish event
        await self._publish_event("file_metadata_updated", {
            "file_id": file_id,
            "updated_fields": list(metadata_update.keys())
        })
        
        return updated_metadata

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get file system statistics.
        
        Returns:
            Dictionary containing file system stats
        """
        total_size = 0
        file_count = 0
        type_counts = {}
        version_count = 0
        
        # Count files and calculate total size
        async for file_path in self._iter_metadata_files():
            try:
                logger.debug(f"Processing metadata file: {file_path}")
                metadata = await self.get_file_metadata(file_path.stem)
                if not metadata.is_deleted:
                    file_count += 1
                    total_size += metadata.size
                    
                    # Count by file type
                    ext = metadata.filename.rsplit('.', 1)[1].lower() if '.' in metadata.filename else 'unknown'
                    type_counts[ext] = type_counts.get(ext, 0) + 1
                    
                    # Count versions
                    versions = await self.get_file_versions(metadata.file_id)
                    version_count += len(versions)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                continue
                
        return {
            "total_files": file_count,
            "total_size": total_size,
            "file_types": type_counts,
            "total_versions": version_count,
            "storage_path": str(self.storage_root)
        }

    async def upload_directory(
        self,
        files: List[UploadFile],
        base_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        overwrite: bool = False
    ) -> List[FileMetadata]:
        """
        Upload a directory of files while maintaining the directory structure.
        
        Args:
            files: List of FastAPI UploadFile objects
            base_path: Optional base path where to store the files
            metadata: Optional file metadata to apply to all files
            overwrite: Whether to overwrite existing files
            
        Returns:
            List of FileMetadata for all uploaded files
            
        Raises:
            ValueError: For invalid files or metadata
            IOError: For file system errors
        """
        uploaded_files = []
        
        for file in files:
            # Skip directories (they'll be created automatically)
            if not file.filename:
                continue
                
            # Construct the full path
            file_path = Path(file.filename)
            if base_path:
                file_path = Path(base_path) / file_path
                
            # Create parent directories if they don't exist
            parent_dir = self.storage_root / file_path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # Upload the file
                file_metadata = await self.upload_file(
                    file=file,
                    metadata=metadata,
                    overwrite=overwrite
                )
                uploaded_files.append(file_metadata)
                
            except Exception as e:
                logger.error(f"Error uploading file {file.filename}: {str(e)}")
                # Continue with other files even if one fails
                continue
                
        return uploaded_files

    async def _iter_metadata_files(self) -> AsyncGenerator[Path, None]:
        """
        Iterate over all metadata files in the main storage and version directories.
        """
        logger.debug(f"_iter_metadata_files: Starting iteration in {self.storage_root}")
        
        # Iterate through main metadata files (e.g., file_id.meta)
        loop = asyncio.get_event_loop()
        for root, dirs, files in await loop.run_in_executor(None, os.walk, self.storage_root / "metadata"):
            for file in files:
                p = Path(root) / file
                if p.is_file() and p.suffix == ".json":
                    yield p
        
        # Iterate through version metadata files (e.g., versions/file_id/vX.meta)
        versions_root = self.storage_root / "metadata"
        if await aios.path.exists(versions_root):
            for root, dirs, files in await loop.run_in_executor(None, os.walk, versions_root):
                for file in files:
                    if file.endswith(".json"):
                        yield Path(root) / file

    async def scan_and_register_existing_files(self) -> int:
        """
        Scans the storage directory for existing files that do not have
        corresponding metadata and registers them with the file manager.
        
        Returns:
            The number of new files registered.
        """
        logger.info(f"Scanning for existing files in {self.storage_root} to register...")
        registered_count = 0
        
        # Get all currently known file IDs from metadata files
        known_file_ids = set()
        async for metadata_path in self._iter_metadata_files():
            try:
                async with aiofiles.open(metadata_path, 'r') as f:
                    content = await f.read()
                metadata = FileMetadata.parse_raw(content)
                known_file_ids.add(metadata.file_id)
            except Exception as e:
                logger.warning(f"Could not read metadata from {metadata_path}: {e}")

        # Walk the storage directory to find actual files
        loop = asyncio.get_event_loop()
        for root, dirs, files in await loop.run_in_executor(None, os.walk, self.storage_root):
            for filename in files:
                file_path = Path(root) / filename
                
                # Calculate the relative path from the storage_root
                relative_file_path = ""
                try:
                    relative_file_path = file_path.relative_to(self.storage_root).as_posix()
                except ValueError as ve:
                    logger.error(f"File path {file_path} is not relative to storage_root {self.storage_root}: {ve}")
                    continue # Skip this file if path is not relative

                if file_path.suffix == ".meta": # Skip metadata files
                    continue
                
                # Check if this file is already registered using its relative path
                is_known = False
                for known_meta_id in known_file_ids:
                    try:
                        known_meta = await self.get_file_metadata(known_meta_id)
                        # Compare against the normalized relative path
                        if known_meta.filename.replace('\\', '/').lower() == relative_file_path.lower():
                            is_known = True
                            break
                    except FileNotFoundError:
                        continue
                    except Exception as known_e:
                        logger.error(f"Error checking known metadata {known_meta_id}: {known_e}")
                        continue
                
                if not is_known:
                    logger.info(f"Found unregistered file: {file_path}")
                    try:
                        # Determine content type using python-magic
                        content_type = "application/octet-stream" # Default to binary
                        try:
                            if file_path.is_file():
                                content_type = magic.from_file(file_path, mime=True)
                        except Exception as magic_e:
                            logger.warning(f"Could not determine content type for {file_path}: {magic_e}")
                        
                        new_file_id = str(uuid.uuid4())
                        checksum = await self._calculate_checksum(file_path)
                        
                        new_metadata = FileMetadata(
                            file_id=new_file_id,
                            filename=relative_file_path,  # Store the relative path
                            content_type=content_type,
                            size=file_path.stat().st_size,
                            checksum=checksum,
                            created_at=file_path.stat().st_ctime,
                            updated_at=file_path.stat().st_mtime,
                            metadata={"source": "scanned_import"},
                            version=1,
                            tags=["imported"],
                            is_deleted=False
                        )
                        
                        await self._save_metadata(new_metadata)
                        # Copy the file to its managed location if it's not already there
                        target_file_path = self._get_file_path(new_file_id)
                        if file_path != target_file_path:
                            # Ensure the target directory exists
                            target_file_path.parent.mkdir(parents=True, exist_ok=True)
                            # Use shutil.copy2 for async copy via asyncio.to_thread
                            await asyncio.to_thread(shutil.copy2, file_path, target_file_path)
                            logger.info(f"Copied {file_path} to managed location {target_file_path}")
                        else:
                            logger.info(f"File {file_path} already in managed location, just registered metadata.")
                            
                        registered_count += 1
                        await self._publish_event("file_registered", new_metadata.model_dump())
                    except Exception as e:
                        logger.error(f"Failed to register file {file_path}: {e}", exc_info=True)
        
        logger.info(f"Finished scanning. Registered {registered_count} new files.")
        return registered_count
                
    async def _find_file_by_checksum(self, checksum: str) -> Optional[FileMetadata]:
        """Find a file metadata by its checksum."""
        async for metadata_path in self._iter_metadata_files():
            try:
                # Extract file_id from metadata_path (e.g., "some_id.meta")
                file_id = metadata_path.stem
                metadata = await self.get_file_metadata(file_id)
                if metadata and metadata.checksum == checksum:
                    return metadata
            except Exception as e:
                logger.warning(f"Error loading metadata from {metadata_path}: {e}")
                continue
        return None

    async def get_file_metadata_by_path(self, relative_path: Union[str, Path]) -> Optional[FileMetadata]:
        """Get file metadata by its relative path (filename)."""
        if isinstance(relative_path, str):
            relative_path = Path(relative_path)

        logger.info(f"FileManager: Attempting to get metadata for path: '{relative_path.as_posix()}'")

        # Iterate through all files and find a match
        all_files = await self.list_files() # list_files returns FileMetadata objects
        for file_metadata in all_files:
            # We need to consider that filename might include subdirectories like 'documents/file.pdf'
            # Normalize both paths to use forward slashes for robust comparison across OS
            if Path(file_metadata.filename).as_posix() == relative_path.as_posix():
                logger.info(f"FileManager: Found file: '{file_metadata.filename}' for requested path: '{relative_path.as_posix()}'")
                return file_metadata
        logger.warning(f"FileManager: File metadata not found for path: '{relative_path.as_posix()}'")
        return None
        
    async def get_file_versions(self, file_id: str) -> List[FileMetadata]:
        """Get all versions of a file."""
        versions = []
        versions_dir = self.storage_root / "versions" / file_id
        
        if not versions_dir.exists():
            return []
            
        for entry in os.scandir(versions_dir):
            if entry.is_file() and entry.name.endswith('.json'):
                try:
                    version = int(entry.name[1:-5])  # Extract version from v1.json
                    metadata = await self.get_file_metadata(file_id, version)
                    versions.append(metadata)
                except (ValueError, json.JSONDecodeError) as e:
                    continue
                    
        return sorted(versions, key=lambda x: x.version)
        
    async def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """Clean up temporary files older than specified hours."""
        temp_dir = self.storage_root / "tmp"
        cutoff = time.time() - (older_than_hours * 3600)
        count = 0
        
        if not temp_dir.exists():
            return 0
            
        for entry in os.scandir(temp_dir):
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                try:
                    await aios.remove(entry.path)
                    count += 1
                except Exception as e:
                    logger.error(f"Error removing temp file {entry.path}: {e}")
                    
        return count

    async def update_access_time(self, file_id: str):
        """Update the last accessed time of a file."""
        metadata = await self.get_file_metadata(file_id)
        if metadata:
            metadata.updated_at = time.time() # Use time.time() for current timestamp
            await self._save_metadata(metadata)
            logger.info(f"Updated access time for file: {file_id}")
        else:
            logger.warning(f"Attempted to update access time for non-existent file: {file_id}")

def get_file_manager() -> FileManager:
    """Dependency for FastAPI to get the file manager instance."""
    return FileManager()