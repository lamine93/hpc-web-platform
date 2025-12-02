# utils/file_manager.py
"""
File system operations for job management.
"""

import os
import logging
from typing import Dict
from datetime import datetime

from ..config.settings import config


logger = logging.getLogger(__name__)


class FileManager:
    """Handles file operations for job scripts and outputs"""
    
    def __init__(self):
        self.base_dir = config.paths.base_user_job_dir
    
    def build_job_paths(self, username: str, job_name: str) -> Dict[str, str]:
        """
        Build per-user directories and paths for job script/output/error.
        
        Args:
            username: User's username
            job_name: Job name
        
        Returns:
            Dictionary with paths: script_loc, output_loc, error_loc, jobs_loc
        """
        # Timestamp to make filenames unique
        timestamp = datetime.now().strftime('%y%m%d%H%M%S')
        
        # Per-user root directory
        user_root = os.path.join(self.base_dir, username)
        
        # Subdirectories
        scripts_dir = os.path.join(user_root, "scripts")
        outputs_dir = os.path.join(user_root, "outputs")
        errors_dir = os.path.join(user_root, "errors")
        jobs_dir = os.path.join(self.base_dir, "jobs")
        
        # Ensure directories exist
        for directory in (scripts_dir, outputs_dir, errors_dir, jobs_dir):
            os.makedirs(directory, exist_ok=True)
        
        # File paths
        script_loc = os.path.join(scripts_dir, f"{job_name}_{timestamp}.sh")
        output_loc = os.path.join(outputs_dir, f"{job_name}_%j.out")
        error_loc = os.path.join(errors_dir, f"{job_name}_%j.err")
        jobs_loc = os.path.join(jobs_dir, "jobs.json")
        
        return {
            "script_loc": script_loc,
            "output_loc": output_loc,
            "error_loc": error_loc,
            "jobs_loc": jobs_loc
        }
    
    def save_script(self, path: str, content: str) -> bool:
        """
        Save job script to file.
        
        Args:
            path: File path
            content: Script content
        
        Returns:
            True if successful
        """
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
            # Make executable
            os.chmod(path, 0o755)
            logger.debug(f"Script saved: {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving script to {path}: {e}")
            return False
    
    def read_file(self, path: str) -> str:
        """
        Read entire file content.
        
        Args:
            path: File path
        
        Returns:
            File content or error message
        """
        if not os.path.exists(path):
            return f"File not found: {path}"
        
        try:
            with open(path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return f"Error reading file: {str(e)}"
    
    def read_file_tail(self, path: str, tail_lines: int = 1000, max_chars: int = 100000) -> str:
        """
        Read the last N lines of a file.
        
        Args:
            path: File path
            tail_lines: Number of lines to read from end
            max_chars: Maximum characters to return
        
        Returns:
            File content or error message
        """
        if not os.path.exists(path):
            return f"File not found: {path}"
        
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
                content = ''.join(lines[-tail_lines:])
                # Limit to max_chars
                return content[-max_chars:]
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return f"Error reading file: {str(e)}"
    
    def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        return os.path.exists(path)
    
    def get_file_size(self, path: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            path: File path
        
        Returns:
            File size or 0 if error
        """
        try:
            return os.path.getsize(path)
        except Exception:
            return 0
    
    def get_file_mtime(self, path: str) -> float:
        """
        Get file modification time.
        
        Args:
            path: File path
        
        Returns:
            Modification timestamp or 0 if error
        """
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0
