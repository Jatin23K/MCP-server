"""
Pydantic Models for FastMCP Server.

This module defines all the Pydantic models used for request/response validation
and data serialization throughout the FastMCP API. These models ensure type safety
and data validation for all API endpoints.
"""

from typing import List, Dict, Any, Optional, Union, Literal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, validator, root_validator, conint, confloat
from typing_extensions import Annotated
from pydantic import field_serializer

# Common base models
class StatusResponse(BaseModel):
    """Standard response model for status messages."""
    success: bool
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()

# Context models
class ContextOperation(str, Enum):
    """Allowed context operations."""
    SET = "set"
    GET = "get"
    DELETE = "delete"
    LIST = "list"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"

class ContextItem(BaseModel):
    """Model for a single context item."""
    key: str = Field(..., description="Unique identifier for the context item")
    value: Any = Field(..., description="The context value (can be any JSON-serializable type)")
    ttl: Optional[int] = Field(
        None,
        ge=1,
        description="Time to live in seconds (optional)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata for the context item"
    )

    class Config:
        schema_extra = {
            "example": {
                "key": "user:123:preferences",
                "value": {"theme": "dark", "notifications": True},
                "ttl": 3600,
                "metadata": {"source": "api", "version": "1.0"}
            }
        }

class ContextBulkOperation(BaseModel):
    """Model for bulk context operations."""
    operation: ContextOperation
    items: List[ContextItem] = Field(
        ...,
        min_items=1,
        description="List of context items to operate on"
    )
    fail_fast: bool = Field(
        True,
        description="If True, stop processing on first error"
    )

class ContextQuery(BaseModel):
    """Model for querying context items."""
    key_prefix: Optional[str] = Field(
        None,
        description="Filter context items by key prefix"
    )
    include_metadata: bool = Field(
        False,
        description="Include metadata in the response"
    )
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of items to return"
    )
    offset: int = Field(
        0,
        ge=0,
        description="Number of items to skip for pagination"
    )

class ContextResponse(StatusResponse):
    """Response model for context operations."""
    data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    count: Optional[int] = None
    total: Optional[int] = None

# File models
class FileType(str, Enum):
    """Supported file types."""
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"

class FileInfo(BaseModel):
    """File information model."""
    name: str
    path: str
    type: FileType
    size: int
    mtime: datetime
    ctime: datetime
    atime: datetime
    content_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer('mtime', 'ctime', 'atime')
    def serialize_datetime_fields(self, dt: datetime) -> str:
        return dt.isoformat()

class FileUpload(BaseModel):
    """Model for file uploads."""
    file: bytes
    filename: str
    content_type: str
    path: Optional[str] = None
    overwrite: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class FileResponseModel(StatusResponse):
    """Response model for file operations."""
    data: Optional[Union[FileInfo, Dict[str, Any], List[FileInfo]]] = None

class FileListResponse(StatusResponse):
    """Response model for listing files."""
    data: List[FileInfo] = Field(default_factory=list, description="List of file information objects")
    total: int = Field(..., description="Total number of files matching the criteria")
    skip: int = Field(0, description="Number of files skipped")
    limit: int = Field(100, description="Maximum number of files returned")

class FileMetadata(BaseModel):
    """Metadata for a file in the system."""
    file_id: str = Field(..., description="Unique identifier for the file")
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type of the file")
    size: int = Field(..., ge=0, description="File size in bytes")
    checksum: str = Field(..., description="SHA-256 checksum of the file")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: List[str] = Field(default_factory=list, description="Tags associated with the file")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the file was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When the file was last updated")
    version: int = Field(1, description="File version number")
    path: str = Field(..., description="Relative path where the file is stored")
    is_deleted: bool = Field(False, description="Whether the file is marked as deleted")
    deleted_at: Optional[datetime] = Field(None, description="When the file was deleted")
    created_by: Optional[str] = Field(None, description="ID of the user who created the file")
    updated_by: Optional[str] = Field(None, description="ID of the user who last updated the file")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
        schema_extra = {
            "example": {
                "file_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "example.pdf",
                "content_type": "application/pdf",
                "size": 1024,
                "checksum": "a1b2c3...",
                "metadata": {"author": "John Doe"},
                "tags": ["document", "pdf"],
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "version": 1,
                "path": "documents/example.pdf",
                "is_deleted": False,
                "deleted_at": None,
                "created_by": "user123",
                "updated_by": "user123"
            }
        }

    @validator('content_type')
    def validate_content_type(cls, v):
        if not v or not v.strip():
            return 'application/octet-stream'
        return v.lower()

    @validator('checksum')
    def validate_checksum(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Checksum must be a non-empty string")
        return v.lower()

    def dict(self, **kwargs):
        # Custom dict method to handle datetime serialization
        d = super().dict(**kwargs)
        for field in ['created_at', 'updated_at', 'deleted_at']:
            if field in d and d[field] is not None:
                if isinstance(d[field], datetime):
                    d[field] = d[field].isoformat()
        return d

class FileVersionInfo(BaseModel):
    """Model for file version information."""
    version: int = Field(..., description="Version number")
    created_at: datetime = Field(..., description="When this version was created")
    size: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="File checksum")
    modified_by: Optional[str] = Field(None, description="User who created this version")
    
    @field_serializer('created_at')
    def serialize_created_at(self, dt: datetime) -> str:
        return dt.isoformat()

class FileVersionListResponse(BaseModel):
    """Response model for listing file versions."""
    file_id: str = Field(..., description="File ID")
    current_version: int = Field(..., description="Current version number")
    versions: List[FileVersionInfo] = Field(default_factory=list, description="List of file versions")

# Event models
class EventType(str, Enum):
    """Event types for the system."""
    CONTEXT_CHANGE = "context_change"
    FILE_CHANGE = "file_change"
    SYSTEM_ALERT = "system_alert"
    API_CALL = "api_call"

class EventSeverity(str, Enum):
    """Event severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class Event(BaseModel):
    """Base event model."""
    event_type: EventType
    source: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO
    correlation_id: Optional[str] = None

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()

class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    timestamp: datetime
    uptime: float
    system: Dict[str, Any]

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()

class MetricType(str, Enum):
    """Metric types for monitoring."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class Metric(BaseModel):
    """Metric model for monitoring."""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    help_text: Optional[str] = None

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()

class ValidationError(BaseModel):
    """Validation error model."""
    loc: List[str]
    msg: str
    type: str

class HTTPValidationError(BaseModel):
    """HTTP validation error response model."""
    detail: List[ValidationError]

class PaginatedResponse(BaseModel):
    """Generic paginated response model."""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int

    class Config:
        arbitrary_types_allowed = True

class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def success(
        cls,
        data: Any = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> "APIResponse":
        return cls(
            success=True,
            data=data,
            meta=meta
        )

    @classmethod
    def error(
        cls,
        message: str,
        code: Optional[str] = None,
        details: Optional[Any] = None,
        status_code: int = 400
    ) -> "APIResponse":
        return cls(
            success=False,
            error={
                "message": message,
                "code": code,
                "details": details,
                "status_code": status_code
            }
        )

class ErrorResponse(BaseModel):
    """Standardized error response model."""
    error: str = Field(..., description="Error type/category")
    detail: str = Field(..., description="Detailed error message")
    timestamp: str = Field(..., description="ISO format timestamp of when the error occurred")
    code: Optional[int] = Field(None, description="Optional error code")
    path: Optional[str] = Field(None, description="Optional request path where error occurred")

# Search models
class SearchResultItem(BaseModel):
    """Model for a single search result item."""
    id: str = Field(..., description="Unique identifier of the search result")
    type: str = Field(..., description="Type of the search result (e.g., file, context)")
    score: float = Field(..., description="Relevance score of the search result")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata for the search result")
    highlight: Optional[Dict[str, List[str]]] = Field(None, description="Optional highlights of matching text")

class SearchResults(BaseModel):
    """Response model for search results."""
    query: str = Field(..., description="The original search query")
    total: int = Field(..., description="Total number of search results")
    items: List[SearchResultItem] = Field(default_factory=list, description="List of search result items")

# User models

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: Optional[str] = Field(None, format="email")
    full_name: Optional[str] = None
    disabled: bool = False

class UserPublic(BaseModel):
    """Public User model (excludes sensitive fields like hashed password)."""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    roles: List[str] = []
    disabled: bool = False

    class Config:
        from_attributes = True # Allow creation from ORM/other objects

class RegisterRequest(BaseModel):
    """Model for user registration request."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    confirm_password: str
    roles: List[str] = Field(default_factory=lambda: ["user"], description="List of roles for the new user (defaults to user)")
    email: Optional[str] = Field(None, format="email")
    full_name: Optional[str] = Field(None, max_length=100)

    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values and v != values['password']:
            raise ValueError('passwords do not match')
        return v