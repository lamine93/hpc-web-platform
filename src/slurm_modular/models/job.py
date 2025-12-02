# models/job.py
"""
Job data model and related utilities.
"""

from dataclasses import dataclass, field,asdict
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum


class JobState(Enum):
    """Slurm job states"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    NODE_FAIL = "NODE_FAIL"
    PREEMPTED = "PREEMPTED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"



@dataclass
class Job:
    """Job data model for Slurm API v0.0.40+"""
    job_id: str
    name: str
    state: JobState
    user: str
    account: Optional[str] = None
    partition: Optional[str] = None
    qos: Optional[str] = None
    nodes: Optional[str] = None  # Node list string (e.g., "hpc")
    node_count: Optional[int] = None
    cpus: Optional[int] = None
    memory: Optional[int] = None  # Memory in MB
    time_limit: Optional[int] = None  # Time limit in minutes
    submit_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    elapsed_time: Optional[str] = None  # Format "HH:MM:SS"
    working_directory: Optional[str] = None
    script_path: Optional[str] = None
    output_path: Optional[str] = None  # stdout_expanded
    error_path: Optional[str] = None   # stderr_expanded
    exit_code: Optional[int] = None
    state_reason: Optional[str] = None
    cluster: Optional[str] = None
    group: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'Job':
        """
        Create a Job instance from Slurm REST API response.
        
        Args:
            data: Raw API response data from /slurmdb/v0.0.40/jobs
        
        Returns:
            Job instance
        
        API Structure:
            {
                "job_id": 3,
                "name": "myjobcpu",
                "user": "slurm",
                "account": "myaccount",
                "partition": "standard",
                "qos": "normal",
                "nodes": "hpc",
                "cluster": "linux",
                "group": "slurm",
                "state": {"current": ["COMPLETED"], "reason": "None"},
                "time": {
                    "elapsed": 600,
                    "submission": 1764465562,
                    "start": 1764465563,
                    "end": 1764466163,
                    "limit": {"set": true, "number": 1440}
                },
                "exit_code": {"return_code": {"set": true, "number": 0}},
                "required": {"CPUs": 1},
                "tres": {"allocated": [
                    {"type": "cpu", "count": 1},
                    {"type": "mem", "count": 7920},
                    {"type": "node", "count": 1}
                ]},
                "stdout_expanded": "/scratch/unknown/myjobcpu-3.out",
                "stderr_expanded": "/scratch/unknown/myjobcpu-3.err",
                "working_directory": "/scratch/unknown"
            }
        """
        from ..utils.formatters import (
            parse_timestamp,
            parse_state_from_dict,
            extract_state_reason,
            format_duration,
            extract_cpus_from_tres,
            extract_memory_from_tres,
            extract_node_count_from_tres,
            extract_exit_code_from_dict,
            extract_time_limit_minutes
        )
        
        # Extract time information
        time_data = data.get('time', {})
        elapsed_seconds = time_data.get('elapsed', 0)
        submission_ts = time_data.get('submission', 0)
        start_ts = time_data.get('start', 0)
        end_ts = time_data.get('end', 0)
        
        # Extract time limit (minutes)
        time_limit = extract_time_limit_minutes(time_data)
        
        # Extract exit code
        exit_code = extract_exit_code_from_dict(data.get('exit_code', {}))
        
        # Extract state and reason
        state_data = data.get('state', {})
        state = parse_state_from_dict(state_data)
        state_reason = extract_state_reason(state_data)
        
        # Extract TRES resources
        tres_allocated = data.get('tres', {}).get('allocated', [])
        cpus = extract_cpus_from_tres(tres_allocated)
        memory = extract_memory_from_tres(tres_allocated)
        node_count = extract_node_count_from_tres(tres_allocated)
        
        # Fallback: extract CPUs from required if not in TRES
        if cpus is None:
            required = data.get('required', {})
            cpus = required.get('CPUs')
        
        return cls(
            job_id=str(data.get('job_id', '')),
            name=data.get('name', 'unknown'),
            state=state,
            user=data.get('user', ''),
            account=data.get('account'),
            partition=data.get('partition'),
            qos=data.get('qos'),
            nodes=data.get('nodes'),
            node_count=node_count,
            cpus=cpus,
            memory=memory,
            time_limit=time_limit,
            submit_time=parse_timestamp(submission_ts),
            start_time=parse_timestamp(start_ts),
            end_time=parse_timestamp(end_ts),
            elapsed_time=format_duration(elapsed_seconds),
            working_directory=data.get('working_directory'),
            output_path=data.get('stdout_expanded'),
            error_path=data.get('stderr_expanded'),
            exit_code=exit_code,
            state_reason=state_reason,
            cluster=data.get('cluster'),
            group=data.get('group'),
            raw_data=data
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for JSON serialization"""
        return {
            'job_id': self.job_id,
            'name': self.name,
            'state': self.state.value if isinstance(self.state, JobState) else str(self.state),
            'user': self.user,
            'account': self.account,
            'partition': self.partition,
            'qos': self.qos,
            'nodes': self.nodes,
            'node_count': self.node_count,
            'cpus': self.cpus,
            'memory': self.memory,
            'time_limit': self.time_limit,
            'submit_time': self.submit_time.isoformat() if self.submit_time else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'elapsed_time': self.elapsed_time,
            'working_directory': self.working_directory,
            'script_path': self.script_path,
            'output_path': self.output_path,
            'error_path': self.error_path,
            'exit_code': self.exit_code,
            'reason': self.state_reason,
            'cluster': self.cluster,
            'group': self.group
        }
    
    def is_terminal_state(self) -> bool:
        """Check if job is in a terminal (finished) state"""
        return self.state in {
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMEOUT,
            JobState.NODE_FAIL
        }
    
    def is_active(self) -> bool:
        """Check if job is currently active (pending or running)"""
        return self.state in {JobState.PENDING, JobState.RUNNING}


@dataclass
class Partition:
    """Partition data model"""
    name: str
    state: Optional[str] = None
    total_nodes: Optional[int] = None
    total_cpus: Optional[int] = None
    default_time: Optional[int] = None  # in minutes
    max_time: Optional[int] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'Partition':
        """Create Partition from API response"""
        return cls(
            name=data.get('name', 'unknown'),
            state=data.get('state'),
            total_nodes=data.get('total_nodes'),
            total_cpus=data.get('total_cpus'),
            default_time=data.get('default_time'),
            max_time=data.get('max_time')
        )


@dataclass
class QOS:
    """Quality of Service data model"""
    name: str
    priority: Optional[int] = None
    max_wall_duration_minutes: Optional[int] = None
    max_jobs_per_user: Optional[int] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'QOS':
        """Create QOS from API response"""
        max_duration = None
        max_time_info = (
            data.get('limits', {})
            .get('max', {})
            .get('wall_clock', {})
            .get('per', {})
            .get('job', {})
        )
        
        if max_time_info.get('set') and not max_time_info.get('infinite'):
            num = max_time_info.get('number')
            if isinstance(num, int) and num > 0:
                max_duration = num
        
        return cls(
            name=data.get('name', 'unknown'),
            priority=data.get('priority'),
            max_wall_duration_minutes=max_duration or 60,  # Default 1 hour
            max_jobs_per_user=data.get('max_jobs_per_user')
        )