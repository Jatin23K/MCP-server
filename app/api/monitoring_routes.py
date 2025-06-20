from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Counter, Histogram, Gauge
import psutil
import time
from typing import Dict, Any
from datetime import datetime

from app.core.file_manager import get_file_manager
from app.core.context_manager import mcp_context_manager

router = APIRouter()

# Metrics
REQUEST_COUNT = Counter(
    'mcp_request_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'mcp_request_latency_seconds',
    'Request latency in seconds',
    ['method', 'endpoint']
)

SYSTEM_MEMORY = Gauge(
    'mcp_system_memory_bytes',
    'System memory usage in bytes'
)

SYSTEM_CPU = Gauge(
    'mcp_system_cpu_percent',
    'System CPU usage percentage'
)

@router.get("/system/status")
async def get_system_status() -> Dict[str, Any]:
    """Get detailed system status."""
    try:
        # Get system metrics
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage('/')
        
        # Update Prometheus metrics
        SYSTEM_MEMORY.set(memory.used)
        SYSTEM_CPU.set(cpu)
        
        # Get file system stats
        file_manager = get_file_manager()
        file_stats = await file_manager.get_stats()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "memory": {
                    "total": memory.total,
                    "used": memory.used,
                    "free": memory.free,
                    "percent": memory.percent
                },
                "cpu": {
                    "percent": cpu
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                }
            },
            "files": file_stats,
            "context": {
                "items": len(await mcp_context_manager.list_context())
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system status: {str(e)}"
        )

@router.get("/system/metrics")
async def get_system_metrics() -> Dict[str, Any]:
    """Get system metrics for monitoring."""
    try:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "requests": {
                    "total": REQUEST_COUNT._value.get(),
                    "latency": REQUEST_LATENCY._sum.get()
                },
                "system": {
                    "memory": SYSTEM_MEMORY._value.get(),
                    "cpu": SYSTEM_CPU._value.get()
                }
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics: {str(e)}"
        ) 