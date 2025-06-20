"""
Context Manager for FastMCP Server.

This module provides a robust context management system that supports:
- In-memory and persistent storage of context items
- TTL (Time-To-Live) for automatic expiration
- Event-based notifications for context changes
- Bulk operations for improved performance
- Thread-safe operations with asyncio support
- Caching for high-performance access
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator, Set, Tuple, Union
from pathlib import Path

import aiofiles
import aiofiles.os
import aioredis
import orjson
from pydantic import ValidationError

from app.models.pydantic_models import ContextItem, ContextOperation, Event, EventType

# Configure logging
logger = logging.getLogger(__name__)

class ContextManager:
    """
    Manages context storage and retrieval with support for TTL, persistence, and event notifications.
    
    Features:
    - In-memory and persistent storage
    - TTL support with automatic cleanup
    - Event-based notifications
    - Thread-safe operations
    - Bulk operations
    - Caching for performance
    """
    
    def __init__(
        self,
        storage_path: str = "data/context",
        redis_url: Optional[str] = None,
        cache_ttl: int = 300,
        max_cache_size: int = 10000,
        persistence_interval: int = 60,
        enable_persistence: bool = True,
        # file_manager: Optional["FileManager"] = None # Add type hint for forward reference
    ):
        """
        Initialize the Context Manager.
        
        Args:
            storage_path: Base directory for persistent storage
            redis_url: Optional Redis URL for distributed caching
            cache_ttl: Time-to-live for cache entries in seconds
            max_cache_size: Maximum number of items to keep in the cache
            persistence_interval: Interval for persisting in-memory data to disk (seconds)
            enable_persistence: Whether to enable disk persistence
            file_manager: Optional FileManager instance for event publishing
        """
        self.storage_path = Path(storage_path)
        self.redis_url = redis_url
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        self.persistence_interval = persistence_interval
        self.enable_persistence = enable_persistence
        
        # In-memory storage
        self._context_store: Dict[str, Dict] = {}
        self._ttl_store: Dict[str, float] = {}
        self._subscriptions: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._cache: Dict[str, Tuple[Any, float]] = {}
        
        # Redis client for distributed caching
        self._redis = None
        self._redis_enabled = bool(redis_url)
        
        # Background tasks
        self._cleanup_task = None
        self._persistence_task = None
        self._is_running = False
        
        # Locks for thread safety
        self._lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()
        
        # Initialize storage
        if self.enable_persistence:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._event_queue = asyncio.Queue()
        # self.file_manager = file_manager # This will be set in main.py if needed
    
    async def initialize(self):
        """Initialize the context manager and start background tasks."""
        if self._is_running:
            return
            
        self._is_running = True
        
        # Initialize Redis if configured
        if self._redis_enabled:
            self._redis = await aioredis.create_redis_pool(self.redis_url)
            logger.info(f"Connected to Redis at {self.redis_url}")
        
        # Load persisted data
        if self.enable_persistence:
            await self._load_persisted_data()
        
        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_loop())
        self._persistence_task = asyncio.create_task(self._persistence_loop())
        
        logger.info("Context Manager initialized")
    
    async def shutdown(self):
        """Shutdown the context manager and cleanup resources."""
        if not self._is_running:
            return
            
        self._is_running = False
        
        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._persistence_task:
            self._persistence_task.cancel()
            try:
                await self._persistence_task
            except asyncio.CancelledError:
                pass
        
        # Close Redis connection
        if self._redis:
            self._redis.close()
            await self._redis.wait_closed()
            self._redis = None
        
        # Persist data before shutdown
        if self.enable_persistence:
            await self._persist_data()
        
        logger.info("Context Manager shut down")
    
    async def set_context(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        notify: bool = True
    ) -> bool:
        """
        Set a context value.
        
        Args:
            key: The context key
            value: The value to store
            ttl: Optional time-to-live in seconds
            metadata: Optional metadata
            notify: Whether to notify subscribers
            
        Returns:
            bool: True if successful, False otherwise
        """
        start_time = time.time()
        logger.debug(f"Attempting to set context for key '{key}'")
        try:
            # Validate input using Pydantic model
            context_item = ContextItem(
                key=key,
                value=value,
                ttl=ttl,
                metadata=metadata or {}
            )
            validation_time = time.time() - start_time
            logger.debug(f"Validation for '{key}' took {validation_time:.4f}s")
            
            async with self._lock:
                lock_acquired_time = time.time()
                logger.debug(f"Lock acquired for '{key}' after {lock_acquired_time - start_time:.4f}s")

                # Store the value
                self._context_store[key] = {
                    "value": context_item.value,
                    "metadata": context_item.metadata,
                    "created_at": time.time(),
                    "updated_at": time.time()
                }
                
                # Set TTL if provided
                if ttl is not None and ttl > 0:
                    self._ttl_store[key] = time.time() + ttl
                elif key in self._ttl_store:
                    del self._ttl_store[key]
                
                store_update_time = time.time()
                logger.debug(f"Store update for '{key}' took {store_update_time - lock_acquired_time:.4f}s")
                
                # Update cache
                await self._update_cache(key, context_item.value)
                cache_update_time = time.time()
                logger.debug(f"Cache update for '{key}' took {cache_update_time - store_update_time:.4f}s")
                
                # Notify subscribers
                if notify:
                    event = Event(
                        event_type=EventType.CONTEXT_CHANGE,
                        source="context_manager",
                        data={
                            "operation": "set",
                            "key": key,
                            "value": value,
                            "metadata": metadata
                        },
                        correlation_id=str(uuid.uuid4())
                    )
                    await self._notify_subscribers(key, event)
                notification_time = time.time()
                logger.debug(f"Notification for '{key}' took {notification_time - cache_update_time:.4f}s")
                
                total_time = time.time() - start_time
                logger.info(f"Successfully set context for key '{key}' in {total_time:.4f}s")
                return True
                
        except ValidationError as e:
            logger.error(f"Validation error setting context {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting context {key}: {e}")
            return False
    
    async def get_context(self, key: str, use_cache: bool = True) -> Optional[Any]:
        """
        Get a context value.
        
        Args:
            key: The context key
            use_cache: Whether to use the cache
            
        Returns:
            The context value or None if not found
        """
        # Check cache first
        if use_cache:
            cached_value = await self._get_from_cache(key)
            if cached_value is not None:
                return cached_value
        
        async with self._lock:
            # Check if key exists and is not expired
            if key not in self._context_store:
                return None
                
            if key in self._ttl_store and self._ttl_store[key] < time.time():
                # Clean up expired key
                await self._delete_context(key, notify=False)
                return None
                
            # Get the value
            item = self._context_store[key]
            value = item["value"]
            
            # Update cache
            await self._update_cache(key, value)
            
            return value
    
    async def delete_context(self, key: str) -> bool:
        """
        Delete a context value.
        
        Args:
            key: The context key
            
        Returns:
            bool: True if deleted, False if not found
        """
        return await self._delete_context(key, notify=True)
    
    async def _delete_context(self, key: str, notify: bool = True) -> bool:
        """Internal method to delete a context value."""
        async with self._lock:
            if key not in self._context_store:
                return False
                
            # Get the old value for notification
            old_value = self._context_store[key]["value"]
            
            # Delete the key
            del self._context_store[key]
            if key in self._ttl_store:
                del self._ttl_store[key]
            
            # Clear from cache
            await self._delete_from_cache(key)
            
            # Notify subscribers
            if notify:
                event = Event(
                    event_type=EventType.CONTEXT_CHANGE,
                    source="context_manager",
                    data={
                        "operation": "delete",
                        "key": key,
                        "old_value": old_value
                    },
                    correlation_id=str(uuid.uuid4())
                )
                await self._notify_subscribers(key, event)
            
            return True
    
    async def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all context keys with the given prefix.
        
        Args:
            prefix: Optional key prefix to filter by
            
        Returns:
            List of matching keys
        """
        async with self._lock:
            now = time.time()
            # Filter by prefix and check TTL
            keys = [
                key for key in self._context_store
                if key.startswith(prefix) and 
                (key not in self._ttl_store or self._ttl_store[key] >= now)
            ]
            return keys
    
    async def bulk_operation(
        self,
        operations: List[Dict[str, Any]],
        fail_fast: bool = True
    ) -> Dict[str, Any]:
        """
        Perform multiple context operations in a single transaction.
        
        Args:
            operations: List of operation dictionaries with 'operation' and other parameters
            fail_fast: Whether to stop on first error
            
        Returns:
            Dictionary with results and any errors
        """
        results = {
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }
        
        for op in operations:
            try:
                op_type = op.get("operation")
                
                if op_type == "set":
                    success = await self.set_context(
                        key=op["key"],
                        value=op["value"],
                        ttl=op.get("ttl"),
                        metadata=op.get("metadata"),
                        notify=False  # We'll notify at the end
                    )
                elif op_type == "delete":
                    success = await self._delete_context(
                        key=op["key"],
                        notify=False  # We'll notify at the end
                    )
                else:
                    raise ValueError(f"Unsupported operation: {op_type}")
                
                if success:
                    results["succeeded"] += 1
                else:
                    results["failed"] += 1
                    if fail_fast:
                        raise Exception("Operation failed and fail_fast is True")
                        
            except Exception as e:
                error_info = {
                    "operation": op,
                    "error": str(e)
                }
                results["errors"].append(error_info)
                results["failed"] += 1
                
                if fail_fast:
                    break
        
        # Notify subscribers of all changes
        if results["succeeded"] > 0:
            event = Event(
                event_type=EventType.CONTEXT_CHANGE,
                source="context_manager",
                data={
                    "operation": "bulk_update",
                    "succeeded": results["succeeded"],
                    "failed": results["failed"]
                },
                correlation_id=str(uuid.uuid4())
            )
            await self._notify_subscribers("", event)
        
        return results
    
    async def subscribe_to_changes(
        self,
        key_prefix: str = "",
        event_types: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to context changes.
        
        Args:
            key_prefix: Only receive events for keys with this prefix
            event_types: List of event types to subscribe to (default: all)
            
        Yields:
            Dictionary with event data
        """
        queue = asyncio.Queue()
        
        # Register the queue
        self._subscriptions[key_prefix].add(queue)
        
        try:
            while True:
                event = await queue.get()
                
                # Filter by event type if specified
                if event_types and event.get("event_type") not in event_types:
                    continue
                    
                yield event
                
        except asyncio.CancelledError:
            pass
        finally:
            # Clean up
            if queue in self._subscriptions[key_prefix]:
                self._subscriptions[key_prefix].remove(queue)
    
    async def _notify_subscribers(self, key: str, event: Event):
        """Notify all subscribers of a context change."""
        # Convert event to dict for serialization
        event_dict = event.dict()
        
        # Find all matching subscriptions
        for prefix, queues in self._subscriptions.items():
            if key.startswith(prefix) or not prefix:
                for queue in queues:
                    try:
                        await queue.put(event_dict)
                    except Exception as e:
                        logger.error(f"Error notifying subscriber: {e}")
    
    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        # Try Redis first if enabled
        if self._redis_enabled and self._redis:
            try:
                cached = await self._redis.get(f"context:{key}")
                if cached:
                    return orjson.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache get error: {e}")
        
        # Fall back to in-memory cache
        async with self._cache_lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if expiry > time.time():
                    return value
                del self._cache[key]
        return None
    
    async def _update_cache(self, key: str, value: Any):
        """Update the cache with a new value."""
        expiry = time.time() + self.cache_ttl
        
        # Update Redis if enabled
        if self._redis_enabled and self._redis:
            try:
                await self._redis.setex(
                    f"context:{key}",
                    self.cache_ttl,
                    orjson.dumps(value)
                )
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")
        
        # Update in-memory cache
        async with self._cache_lock:
            # If cache is full, remove oldest items
            if len(self._cache) >= self.max_cache_size:
                # Remove the oldest 10% of items
                items_to_remove = max(1, self.max_cache_size // 10)
                oldest_keys = sorted(
                    self._cache.keys(),
                    key=lambda k: self._cache[k][1]
                )[:items_to_remove]
                for k in oldest_keys:
                    del self._cache[k]
            
            self._cache[key] = (value, expiry)
    
    async def _delete_from_cache(self, key: str):
        """Delete a key from the cache."""
        # Delete from Redis if enabled
        if self._redis_enabled and self._redis:
            try:
                await self._redis.delete(f"context:{key}")
            except Exception as e:
                logger.warning(f"Redis cache delete error: {e}")
        
        # Delete from in-memory cache
        async with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
    
    async def _cleanup_expired_loop(self):
        """Background task to clean up expired keys."""
        while self._is_running:
            try:
                now = time.time()
                expired_keys = [
                    key for key, expiry in self._ttl_store.items()
                    if expiry <= now
                ]
                
                for key in expired_keys:
                    await self._delete_context(key)
                
                # Sleep for a while before next cleanup
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(5)  # Avoid tight loop on errors
    
    async def _persistence_loop(self):
        """Background task to persist in-memory data to disk."""
        if not self.enable_persistence:
            return
            
        while self._is_running:
            try:
                await asyncio.sleep(self.persistence_interval)
                await self._persist_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in persistence task: {e}")
                await asyncio.sleep(5)  # Avoid tight loop on errors
    
    async def _persist_data(self):
        """Persist in-memory data to disk."""
        if not self.enable_persistence:
            return
            
        persist_start_time = time.time()
        logger.debug("Starting persistence of context data...")
        try:
            # Create a snapshot of the current state
            async with self._lock:
                snapshot = {
                    "context_store": self._context_store,
                    "ttl_store": self._ttl_store,
                    "timestamp": time.time()
                }
            snapshot_time = time.time()
            logger.debug(f"Snapshot created in {snapshot_time - persist_start_time:.4f}s")

            # Convert snapshot to JSON bytes using orjson for speed
            loop = asyncio.get_event_loop()
            json_data = await loop.run_in_executor(None, orjson.dumps, snapshot)
            serialization_time = time.time()
            logger.debug(f"Serialization took {serialization_time - snapshot_time:.4f}s")
            
            # Write to a temporary file first
            temp_path = self.storage_path / "context.tmp"
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(json_data)
            temp_write_time = time.time()
            logger.debug(f"Temp file write took {temp_write_time - serialization_time:.4f}s")
            
            # Atomic rename
            final_path = self.storage_path / "context.json"
            await aiofiles.os.replace(temp_path, final_path)
            rename_time = time.time()
            logger.debug(f"Atomic rename took {rename_time - temp_write_time:.4f}s")
            
            total_persist_time = time.time() - persist_start_time
            logger.debug(f"Successfully persisted context data to {final_path} in {total_persist_time:.4f}s")
            
        except Exception as e:
            logger.error(f"Error persisting context data: {e}")
    
    async def _load_persisted_data(self):
        """
        Load persisted data from disk."""
        if not self.enable_persistence:
            return
            
        load_start_time = time.time()
        logger.debug("Starting to load persisted context data...")
            
        try:
            final_path = self.storage_path / "context.json"
            if not final_path.exists():
                logger.info("No persisted context data found")
                return
                
            async with aiofiles.open(final_path, "r") as f:
                raw_data = await f.read()
            file_read_time = time.time()
            logger.debug(f"Read persisted data file in {file_read_time - load_start_time:.4f}s")

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, orjson.loads, raw_data)
            deserialization_time = time.time()
            logger.debug(f"Deserialization took {deserialization_time - file_read_time:.4f}s")
                
            async with self._lock:
                self._context_store = data.get("context_store", {})
                self._ttl_store = data.get("ttl_store", {})
                
            total_load_time = time.time() - load_start_time
            logger.info(f"Loaded {len(self._context_store)} context items from disk in {total_load_time:.4f}s")
            
        except Exception as e:
            logger.error(f"Error loading persisted context data: {e}")

    async def _get_item_data_from_store(self, key: str) -> Optional[Dict[str, Any]]:
        """Internal helper to get raw item data from the context store."""
        async with self._lock:
            return self._context_store.get(key)

    async def get_context_item_details(self, key: str) -> Optional[ContextItem]:
        """
        Get a full ContextItem object by key, including its TTL and timestamps.
        """
        item_data = await self._get_item_data_from_store(key)
        if not item_data:
            return None

        async with self._lock:
            ttl_value = self._ttl_store.get(key)

        return ContextItem(
            key=key,
            value=item_data["value"],
            ttl=int(ttl_value - time.time()) if ttl_value else None, # Convert remaining TTL to int
            metadata=item_data["metadata"],
            # Assuming ContextItem supports created_at and updated_at directly, if not, they'll be in metadata
            # For now, these are not directly in the ContextItem pydantic model, so we won't pass them directly
            # created_at=datetime.fromtimestamp(item_data["created_at"]),
            # updated_at=datetime.fromtimestamp(item_data["updated_at"])
        )

    async def list_all_context_items_full(
        self,
        prefix: str = "",
        skip: int = 0,
        limit: int = 100
    ) -> List[ContextItem]:
        """
        List all context items with full details, supporting prefix filtering and pagination.
        """
        all_keys = await self.list_keys(prefix=prefix)
        
        # Apply skip and limit for pagination on keys
        paginated_keys = all_keys[skip : skip + limit]
        
        full_items = []
        for key in paginated_keys:
            item = await self.get_context_item_details(key)
            if item:
                full_items.append(item)
        return full_items

    async def count_all_context_items(self, prefix: str = "") -> int:
        """
        Count all context items matching a prefix.
        """
        all_keys = await self.list_keys(prefix=prefix)
        return len(all_keys)

    async def publish_event(self, event: Event):
        """Publish an event to all subscribers."""
        try:
            await self._event_queue.put(event)
            logger.debug(f"Event published: {event.event_type}")
        except Exception as e:
            logger.error(f"Error publishing event: {e}", exc_info=True)

    async def _process_events(self):
        """Process events from the queue."""
        while self._is_running:
            try:
                event = await self._event_queue.get()
                for subscriber in self._subscribers:
                    try:
                        await subscriber(event)
                    except Exception as e:
                        logger.error(f"Error processing event in subscriber: {e}", exc_info=True)
                self._event_queue.task_done()
            except Exception as e:
                logger.error(f"Error in event processing loop: {e}", exc_info=True)

    def subscribe(self, callback):
        """Subscribe to events."""
        self._subscribers.add(callback)
        return lambda: self._subscribers.remove(callback)

    async def get_context(self) -> Dict[str, Any]:
        """Get the current application context."""
        return {
            "timestamp": time.time(),
            "subscribers": len(self._subscribers),
            "queue_size": self._event_queue.qsize()
        }

    def set_file_manager(self, file_manager: "FileManager"):
        """Set the file manager instance for event publishing."""
        self.file_manager = file_manager
        logger.info("File manager reference set in context manager")

    async def cleanup(self):
        """Clean up resources."""
        self._is_running = False
        # Clean up any resources here
        logger.info("ContextManager cleaned up")

# Global instance
mcp_context_manager = ContextManager()

# Initialize function for dependency injection
async def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    if not hasattr(mcp_context_manager, '_is_running') or not mcp_context_manager._is_running:
        await mcp_context_manager.initialize()
    return mcp_context_manager