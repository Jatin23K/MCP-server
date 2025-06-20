"""
Script to fix metadata files by ensuring both root and version metadata exist.
"""

import asyncio
import logging
from pathlib import Path
import shutil
import json
import sys
import os

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from app.core.file_manager import FileManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_metadata_files():
    """Fix metadata files by ensuring both root and version metadata exist."""
    file_manager = FileManager()
    storage_root = Path(file_manager.storage_root)
    versions_dir = storage_root / "versions"
    
    if not versions_dir.exists():
        logger.info("No versions directory found, nothing to fix.")
        return
        
    fixed_count = 0
    error_count = 0
    
    # Walk through version directories
    for version_dir in versions_dir.iterdir():
        if not version_dir.is_dir():
            continue
            
        file_id = version_dir.name
        version_meta = version_dir / "v1.meta"
        
        if not version_meta.exists():
            continue
            
        try:
            # Read version metadata
            with open(version_meta, 'r') as f:
                metadata = json.load(f)
                
            # Create root metadata
            root_meta = storage_root / f"{file_id}.meta"
            with open(root_meta, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            fixed_count += 1
            logger.info(f"Fixed metadata for file {file_id}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Error fixing metadata for file {file_id}: {e}")
            
    logger.info(f"Metadata fix completed. Fixed {fixed_count} files, {error_count} errors.")

if __name__ == "__main__":
    asyncio.run(fix_metadata_files()) 
