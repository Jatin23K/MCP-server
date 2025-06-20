"""Streaming Routes for FastMCP Server.

This module provides Server-Sent Events (SSE) streaming endpoints for real-time
updates from the FastMCP server. It allows clients to subscribe to various
event streams including context changes, file updates, and system events.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional, Any, Union
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, AnyHttpUrl, field_serializer

from app.core.context_manager import mcp_context_manager
from app.core.file_manager import FileManager, get_file_manager

# Initialize router
router = APIRouter(
    prefix="/api/v1",
    tags=["streams"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_403_FORBIDDEN: {"description": "Not enough permissions"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Rate limit exceeded"},
    }
)

# Configure logging
logger = logging.getLogger(__name__)

class StreamEvent(BaseModel):
    """Base model for all stream events."""
    event: str
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def sse_format(self) -> str:
        """Format the event as an SSE message."""
        lines = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event is not None:
            lines.append(f"event: {self.event}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        
        # Ensure data is a JSON string
        if isinstance(self.data, (dict, list)):
            data_str = json.dumps(self.data, default=str)
        else:
            data_str = str(self.data)
            
        # Split data by lines and add 'data: ' prefix to each
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
            
        # Add empty line to indicate end of event
        lines.append("")
        return "\n".join(lines)

class ContextStreamEvent(BaseModel):
    """Model for context change events."""
    type: str = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()

async def context_event_generator(
    request: Request,
    key_prefix: Optional[str] = None,
    event_types: Optional[List[str]] = None
) -> AsyncGenerator[StreamEvent, None]:
    """Generate context change events."""
    try:
        # Send initial connection event
        yield StreamEvent(
            event="connected",
            data={
                "message": "Connected to context event stream",
                "timestamp": datetime.utcnow().isoformat(),
                "key_prefix": key_prefix,
                "event_types": event_types or ["*"]
            }
        )

        # Subscribe to context changes
        async for event in mcp_context_manager.subscribe_to_changes(
            key_prefix=key_prefix,
            event_types=event_types
        ):
            if await request.is_disconnected():
                logger.debug("Client disconnected from context event stream")
                break

            try:
                # Create and yield the event
                stream_event = StreamEvent(
                    event=event.get("event_type", "change"),
                    data={
                        "key": event.get("key"),
                        "value": event.get("value"),
                        "old_value": event.get("old_value"),
                        "timestamp": event.get("timestamp"),
                        "metadata": event.get("metadata", {})
                    },
                    id=event.get("event_id")
                )
                yield stream_event

            except Exception as e:
                logger.error(f"Error processing context event: {str(e)}")
                yield StreamEvent(
                    event="error",
                    data={
                        "message": "Error processing event",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

    except asyncio.CancelledError:
        logger.debug("Context event generator was cancelled")
        raise
    except Exception as e:
        logger.exception("Error in context event generator")
        yield StreamEvent(
            event="error",
            data={
                "message": "Error in event stream",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    finally:
        logger.info("Context event stream closed")

async def file_event_generator(
    request: Request,
    path_prefix: Optional[str] = None,
    event_types: Optional[List[str]] = None
) -> AsyncGenerator[StreamEvent, None]:
    """Generate file system events."""
    try:
        # Send initial connection event
        yield StreamEvent(
            event="connected",
            data={
                "message": "Connected to file event stream",
                "timestamp": datetime.utcnow().isoformat(),
                "path_prefix": path_prefix,
                "event_types": event_types or ["*"]
            }
        )

        # Subscribe to file system events
        async for event in get_file_manager().subscribe_to_events(
            path_prefix=path_prefix,
            event_types=event_types
        ):
            if await request.is_disconnected():
                logger.debug("Client disconnected from file event stream")
                break

            try:
                # Create and yield the event
                stream_event = StreamEvent(
                    event=event.get("event_type", "file_change"),
                    data={
                        "path": event.get("path"),
                        "type": event.get("type"),
                        "size": event.get("size"),
                        "timestamp": event.get("timestamp"),
                        "metadata": event.get("metadata", {})
                    },
                    id=event.get("event_id")
                )
                yield stream_event

            except Exception as e:
                logger.error(f"Error processing file event: {str(e)}")
                yield StreamEvent(
                    event="error",
                    data={
                        "message": "Error processing file event",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

    except asyncio.CancelledError:
        logger.debug("File event generator was cancelled")
        raise
    except Exception as e:
        logger.exception("Error in file event generator")
        yield StreamEvent(
            event="error",
            data={
                "message": "Error in file event stream",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    finally:
        logger.info("File event stream closed")

@router.get(
    "/stream/context",
    response_class=StreamingResponse,
    summary="Subscribe to context changes",
    description="""
    Establishes a Server-Sent Events (SSE) stream that sends real-time updates
    when context values change in the system.
    
    Query Parameters:
    - key_prefix: Filter events to keys with this prefix
    - event_types: Comma-separated list of event types to subscribe to (create,update,delete)
    """
)
async def stream_context_changes(
    request: Request,
    key_prefix: Optional[str] = None,
    event_types: str = None
):
    """
    Stream context changes as Server-Sent Events.
    
    This endpoint maintains a persistent connection and sends events whenever
    context values are created, updated, or deleted.
    """
    # Parse event types
    event_types_list = None
    if event_types:
        event_types_list = [et.strip() for et in event_types.split(",") if et.strip()]
    
    # Create the event generator
    event_generator = context_event_generator(
        request=request,
        key_prefix=key_prefix,
        event_types=event_types_list
    )
    
    # Return the SSE response
    return EventSourceResponse(
        event_generator,
        ping=30,  # Send keep-alive ping every 30 seconds
        ping_message_factory=lambda: StreamEvent(
            event="ping",
            data={"timestamp": datetime.utcnow().isoformat()}
        ).sse_format()
    )

@router.get(
    "/stream/files",
    response_class=StreamingResponse,
    summary="Subscribe to file system events",
    description="""
    Establishes a Server-Sent Events (SSE) stream that sends real-time updates
    for file system events like file creation, modification, and deletion.
    
    Query Parameters:
    - path_prefix: Filter events to paths with this prefix
    - event_types: Comma-separated list of event types to subscribe to (create,modify,delete)
    """
)
async def stream_file_events(
    request: Request,
    path_prefix: Optional[str] = None,
    event_types: str = None
):
    """
    Stream file system events as Server-Sent Events.
    
    This endpoint maintains a persistent connection and sends events whenever
    files are created, modified, or deleted in the monitored directories.
    """
    # Parse event types
    event_types_list = None
    if event_types:
        event_types_list = [et.strip() for et in event_types.split(",") if et.strip()]
    
    # Create the event generator
    event_generator = file_event_generator(
        request=request,
        path_prefix=path_prefix,
        event_types=event_types_list
    )
    
    # Return the SSE response
    return EventSourceResponse(
        event_generator,
        ping=30,  # Send keep-alive ping every 30 seconds
        ping_message_factory=lambda: StreamEvent(
            event="ping",
            data={"timestamp": datetime.utcnow().isoformat()}
        ).sse_format()
    )

@router.get(
    "/stream/all",
    response_class=StreamingResponse,
    summary="Subscribe to all events",
    description="""
    Establishes a Server-Sent Events (SSE) stream that combines context changes
    and file system events into a single stream.
    """
)
async def stream_all_events(
    request: Request,
    key_prefix: Optional[str] = None,
    path_prefix: Optional[str] = None,
    context_event_types: str = None,
    file_event_types: str = None
):
    """
    Stream all system events as Server-Sent Events.
    
    This combines both context changes and file system events into a single
    event stream. Events can be filtered using the provided parameters.
    """
    # Parse event types
    context_event_types_list = None
    if context_event_types:
        context_event_types_list = [et.strip() for et in context_event_types.split(",") if et.strip()]
    
    file_event_types_list = None
    if file_event_types:
        file_event_types_list = [et.strip() for et in file_event_types.split(",") if et.strip()]

    async def combined_generator():
        # Create queues for the different event types
        context_queue = asyncio.Queue()
        file_queue = asyncio.Queue()

        # Start context event consumer
        async def consume_context_events():
            try:
                async for event in context_event_generator(
                    request=request,
                    key_prefix=key_prefix,
                    event_types=context_event_types_list
                ):
                    if await request.is_disconnected():
                        break
                    await context_queue.put(("context", event))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error in context event consumer: {str(e)}")
            finally:
                await context_queue.put(None)  # Signal completion

        # Start file event consumer
        async def consume_file_events():
            try:
                async for event in file_event_generator(
                    request=request,
                    path_prefix=path_prefix,
                    event_types=file_event_types_list
                ):
                    if await request.is_disconnected():
                        break
                    await file_queue.put(("file", event))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error in file event consumer: {str(e)}")
            finally:
                await file_queue.put(None)  # Signal completion

        # Start the consumers
        context_task = asyncio.create_task(consume_context_events())
        file_task = asyncio.create_task(consume_file_events())

        try:
            # Send initial event
            yield StreamEvent(
                event="connected",
                data={
                    "message": "Connected to combined event stream",
                    "timestamp": datetime.utcnow().isoformat(),
                    "key_prefix": key_prefix,
                    "path_prefix": path_prefix,
                    "context_event_types": context_event_types_list or ["*"],
                    "file_event_types": file_event_types_list or ["*"]
                }
            )

            # Process events from both queues
            context_done = False
            file_done = False

            while not (context_done and file_done):
                # Wait for events from either queue
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(context_queue.get()) if not context_done else None,
                        asyncio.create_task(file_queue.get()) if not file_done else None
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Process completed tasks
                for task in done:
                    try:
                        result = task.result()
                        if result is None:
                            # One of the queues is done
                            if not context_done and task == context_task:
                                context_done = True
                            elif not file_done and task == file_task:
                                file_done = True
                            continue
                            
                        # Yield the event
                        source, event = result
                        event.data["_source"] = source
                        yield event
                        
                    except Exception as e:
                        logger.error(f"Error processing event: {str(e)}")
                        yield StreamEvent(
                            event="error",
                            data={
                                "message": "Error processing event",
                                "error": str(e),
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        )

        except asyncio.CancelledError:
            logger.debug("Combined event stream was cancelled")
            raise
        finally:
            # Clean up tasks
            if not context_task.done():
                context_task.cancel()
            if not file_task.done():
                file_task.cancel()
            
            try:
                await asyncio.gather(context_task, file_task, return_exceptions=True)
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")

    # Return the SSE response
    return EventSourceResponse(
        combined_generator(),
        ping=30,  # Send keep-alive ping every 30 seconds
        ping_message_factory=lambda: StreamEvent(
            event="ping",
            data={"timestamp": datetime.utcnow().isoformat()}
        ).sse_format()
    )