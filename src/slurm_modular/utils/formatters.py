# utils/formatters.py
"""
Data formatting utilities for timestamps, durations, etc.
"""

from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any, List
import logging

from ..models.job import JobState


logger = logging.getLogger(__name__)


def parse_timestamp(ts_input: Union[int, Dict, None]) -> Optional[datetime]:
    """
    Converts various Slurm timestamp formats to datetime.
    
    Handles:
    - int: Unix timestamp
    - {"number": int}: Object with timestamp
    - {"set": bool, "number": int}: Object with set flag
    
    Args:
        ts_input: Timestamp in various formats
    
    Returns:
        datetime object or None
    """
    if ts_input is None:
        return None
    
    # Handle dict with 'number' key
    if isinstance(ts_input, dict):
        if not ts_input.get('set', True):  # If set is False, no timestamp
            return None
        ts = ts_input.get('number', 0)
    else:
        ts = ts_input
    
    if ts is None or ts <= 0:
        return None
    
    try:
        return datetime.fromtimestamp(ts)
    except (ValueError, OSError) as e:
        logger.warning(f"Invalid timestamp: {ts_input}")
        return None


def format_timestamp(dt: Optional[datetime], format_str: str = "%d/%m/%Y %H:%M:%S") -> str:
    """
    Format datetime to string.
    
    Args:
        dt: datetime object
        format_str: strftime format string
    
    Returns:
        Formatted string or "N/A"
    """
    if dt is None:
        return "N/A"
    
    try:
        return dt.strftime(format_str)
    except Exception as e:
        logger.warning(f"Error formatting timestamp: {e}")
        return "N/A"


def format_duration(seconds: Union[int, float, None]) -> str:
    """
    Converts elapsed seconds into readable format (D:HH:MM:SS or HH:MM:SS).
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string
    """
    if seconds is None or seconds <= 0:
        return "N/A"
    
    try:
        td = timedelta(seconds=int(seconds))
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except Exception as e:
        logger.warning(f"Error formatting duration: {e}")
        return "N/A"


def format_memory(memory_mb: Union[int, float, None]) -> str:
    """
    Format memory size to human-readable format.
    
    Args:
        memory_mb: Memory in megabytes
    
    Returns:
        Formatted memory string (e.g., "2.5 GB", "512 MB")
    """
    if memory_mb is None or memory_mb <= 0:
        return "N/A"
    
    try:
        if memory_mb >= 1024:
            return f"{memory_mb / 1024:.2f} GB"
        else:
            return f"{memory_mb:.0f} MB"
    except Exception:
        return "N/A"


def parse_state(state_input: Union[str, Dict, None]) -> JobState:
    """
    Parse job state from various formats.
    
    Args:
        state_input: State as string or dict
    
    Returns:
        JobState enum value
    """
    if state_input is None:
        return JobState.UNKNOWN
    
    # Handle dict format
    if isinstance(state_input, dict):
        state_str = state_input.get('current', state_input.get('name', 'UNKNOWN'))
    else:
        state_str = str(state_input)
    
    # Normalize state string
    state_str = state_str.upper().strip()
    
    # Map to enum
    try:
        return JobState[state_str]
    except KeyError:
        logger.warning(f"Unknown job state: {state_str}")
        return JobState.UNKNOWN


def format_cpus(cpus_input: Union[int, Dict, None]) -> str:
    """
    Format CPU count from various formats.
    
    Args:
        cpus_input: CPU count as int or dict
    
    Returns:
        Formatted CPU string
    """
    if cpus_input is None:
        return "N/A"
    
    if isinstance(cpus_input, dict):
        cpus = cpus_input.get('number', 0)
    else:
        cpus = cpus_input
    
    return str(cpus) if cpus > 0 else "N/A"


def format_nodes(nodes_input: Union[int, Dict, None]) -> str:
    """
    Format node count from various formats.
    
    Args:
        nodes_input: Node count as int or dict
    
    Returns:
        Formatted node string
    """
    if nodes_input is None:
        return "N/A"
    
    if isinstance(nodes_input, dict):
        nodes = nodes_input.get('number', 0)
    else:
        nodes = nodes_input
    
    return str(nodes) if nodes > 0 else "N/A"


def safe_get(obj: Any, *keys, default=None) -> Any:
    """
    Safely navigate nested dictionaries.
    
    Args:
        obj: Object to navigate
        *keys: Keys to traverse
        default: Default value if not found
    
    Returns:
        Value at nested key or default
    """
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            return default
    return obj if obj is not None else default


def format_exit_code(exit_code: Union[int, Dict, None]) -> str:
    """
    Format exit code with interpretation.
    
    Args:
        exit_code: Exit code as int or dict
    
    Returns:
        Formatted exit code string
    """
    if exit_code is None:
        return "N/A"
    
    if isinstance(exit_code, dict):
        status = exit_code.get('status', {})
        if isinstance(status, dict):
            code = status.get('number', 0)
        else:
            code = exit_code.get('return_code', 0)
    else:
        code = exit_code
    
    if code == 0:
        return "0 (Success)"
    else:
        return f"{code} (Error)"


def humanize_number(num: Union[int, float, None]) -> str:
    """
    Convert large numbers to human-readable format.
    
    Args:
        num: Number to format
    
    Returns:
        Formatted string (e.g., "1.2K", "3.4M")
    """
    if num is None:
        return "N/A"
    
    try:
        num = float(num)
        if num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return f"{num:.0f}"
    except Exception:
        return "N/A"


def extract_from_tres(tres_data: Union[List[Dict], None], resource_type: str) -> Optional[int]:
    """
    Extract resource count from TRES allocated data.
    
    Args:
        tres_data: List of TRES resources
        resource_type: Type of resource ('cpu', 'mem', 'node', etc.)
    
    Returns:
        Resource count or None if not found
    
    Examples:
        >>> tres = [{"type": "cpu", "count": 4}, {"type": "mem", "count": 8000}]
        >>> extract_from_tres(tres, 'cpu')
        4
    """
    if not isinstance(tres_data, list):
        return None
    
    for resource in tres_data:
        if isinstance(resource, dict) and resource.get('type') == resource_type:
            return resource.get('count')
    
    return None


def extract_cpus_from_tres(tres_data: Union[List[Dict], None]) -> Optional[int]:
    """Extract CPU count from TRES allocated data."""
    return extract_from_tres(tres_data, 'cpu')


def extract_memory_from_tres(tres_data: Union[List[Dict], None]) -> Optional[int]:
    """Extract memory (MB) from TRES allocated data."""
    return extract_from_tres(tres_data, 'mem')


def extract_node_count_from_tres(tres_data: Union[List[Dict], None]) -> Optional[int]:
    """Extract node count from TRES allocated data."""
    return extract_from_tres(tres_data, 'node')


def extract_exit_code_from_dict(exit_code_data: Union[Dict, None]) -> Optional[int]:
    """
    Extract exit code from API exit_code dict.
    
    Args:
        exit_code_data: Exit code dict from API
            Format: {"return_code": {"set": True, "number": 0}}
    
    Returns:
        Exit code number or None
    """
    if not isinstance(exit_code_data, dict):
        return None
    
    return_code = exit_code_data.get('return_code', {})
    if isinstance(return_code, dict) and return_code.get('set'):
        return return_code.get('number')
    
    return None


def extract_time_limit_minutes(time_data: Union[Dict, None]) -> Optional[int]:
    """
    Extract time limit from time data.
    
    Args:
        time_data: Time dict from API
            Format: {"limit": {"set": True, "infinite": False, "number": 1440}}
    
    Returns:
        Time limit in minutes or None
    """
    if not isinstance(time_data, dict):
        return None
    
    limit_data = time_data.get('limit', {})
    if isinstance(limit_data, dict):
        if limit_data.get('set') and not limit_data.get('infinite'):
            return limit_data.get('number')
    
    return None


def parse_state_from_dict(state_data: Union[str, Dict, List, None]) -> JobState:
    """
    Parse job state from various API formats.
    
    Handles:
    - String: "COMPLETED"
    - Dict: {"current": ["COMPLETED"], "reason": "None"}
    - List: ["COMPLETED"]
    
    Args:
        state_data: State in various formats
    
    Returns:
        JobState enum value
    """
    if state_data is None:
        return JobState.UNKNOWN
    
    # Handle dict format with 'current' key
    if isinstance(state_data, dict):
        current = state_data.get('current', [])
        if isinstance(current, list) and current:
            state_str = current[0]
        elif isinstance(current, str):
            state_str = current
        else:
            state_str = 'UNKNOWN'
    # Handle list format
    elif isinstance(state_data, list):
        state_str = state_data[0] if state_data else 'UNKNOWN'
    # Handle string format
    else:
        state_str = str(state_data)
    
    # Normalize and map to enum
    state_str = state_str.upper().strip()
    
    try:
        return JobState[state_str]
    except KeyError:
        logger.warning(f"Unknown job state: {state_str}")
        return JobState.UNKNOWN


def extract_state_reason(state_data: Union[Dict, None]) -> Optional[str]:
    """
    Extract state reason from state dict.
    
    Args:
        state_data: State dict from API
            Format: {"current": ["COMPLETED"], "reason": "None"}
    
    Returns:
        State reason string or None
    """
    if isinstance(state_data, dict):
        reason = state_data.get('reason')
        if reason and reason != 'None':
            return reason
    return None