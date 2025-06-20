"""
Data Processing Routes for FastMCP Server.

This module provides API endpoints for:
- File content extraction
- Data validation
- Batch processing
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
import os

from app.core.data_processor import data_processor
from app.core.file_manager import get_file_manager

router = APIRouter()
logger = logging.getLogger(__name__)

class ProcessingSchema(BaseModel):
    """Schema for data validation."""
    type: str
    required: Optional[List[str]] = None
    properties: Optional[Dict[str, Any]] = None

class ProcessingResponse(BaseModel):
    """Response model for processing operations."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

@router.post("/process/extract")
async def extract_file_content(
    file: UploadFile = File(...),
    include_metadata: bool = False
) -> ProcessingResponse:
    """
    Extract content from a file.
    
    - **file**: The file to process
    - **include_metadata**: Whether to include file metadata in response
    """
    try:
        # Save file temporarily
        temp_path = f"data/tmp/{file.filename}"
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # Extract content
        file_type = file.filename.rsplit('.', 1)[1].lower()
        content = await data_processor.extract_content(temp_path, file_type)
        
        # Add metadata if requested
        if include_metadata:
            file_manager = get_file_manager()
            metadata = await file_manager.get_file_metadata(file.filename)
            content["metadata"] = metadata.dict()
            
        return ProcessingResponse(
            success=True,
            message="Content extracted successfully",
            data=content
        )
        
    except Exception as e:
        logger.error(f"Error extracting content: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract content: {str(e)}"
        )
        
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

@router.post("/process/validate")
async def validate_data(
    data: Dict[str, Any],
    schema: ProcessingSchema
) -> ProcessingResponse:
    """
    Validate data against a schema.
    
    - **data**: The data to validate
    - **schema**: Validation schema
    """
    try:
        result = await data_processor.validate_data(data, schema.dict())
        return ProcessingResponse(
            success=result["valid"],
            message="Validation completed",
            data=result
        )
    except Exception as e:
        logger.error(f"Error validating data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )

@router.post("/process/batch")
async def process_batch(
    files: List[UploadFile] = File(...),
    processor_type: str = "extract",
    schema: Optional[ProcessingSchema] = None
) -> ProcessingResponse:
    """
    Process a batch of files.
    
    - **files**: List of files to process
    - **processor_type**: Type of processing to apply
    - **schema**: Optional validation schema
    """
    try:
        result = await data_processor.process_batch(
            files=files,
            processor_type=processor_type,
            schema=schema.dict() if schema else None
        )
        return ProcessingResponse(
            success=result["failed"] == 0,
            message=f"Processed {result['processed']} files, {result['failed']} failed",
            data=result
        )
    except Exception as e:
        logger.error(f"Error processing batch: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch processing failed: {str(e)}"
        ) 