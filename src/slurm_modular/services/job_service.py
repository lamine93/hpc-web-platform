# services/job_service.py
"""
Job management service layer.
Business logic for job operations.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..models.job import Job, Partition, QOS
from ..api.slurm_client import get_client
from ..config.settings import config
from ..utils.file_manager import FileManager


logger = logging.getLogger(__name__)


class JobService:
    """
    Service layer for job management.
    Handles business logic and coordinates between API client and storage.
    """
    
    def __init__(self):
        self.api_client = get_client()
        self.file_manager = FileManager()
        self._job_cache: Dict[str, Job] = {}
        self._partitions_cache: List[Partition] = []
        self._qos_cache: List[QOS] = []
    
    # ===== Job Operations =====
    
    def get_all_jobs(self, start_time: Optional[str] = None) -> List[Job]:
        """
        Get all jobs, optionally filtered by user.
        
        Args:
            user: Optional username filter
        
        Returns:
            List of Job objects
        """
        try:
            raw_jobs = self.api_client.get_jobs(start_time=start_time)
            jobs = [Job.from_api_response(raw) for raw in raw_jobs]
            
            # Update cache
            for job in jobs:
                self._job_cache[job.job_id] = job
            
            return jobs
        except Exception as e:
            logger.error(f"Error getting jobs: {e}")
            return []
    
    def get_job_by_id(self, job_id: str, force_refresh: bool = False) -> Optional[Job]:
        """
        Get a specific job by ID.
        
        Args:
            job_id: Job ID
            force_refresh: If True, bypass cache and fetch from API
        
        Returns:
            Job object or None
        """
        # Check cache first
        if not force_refresh and job_id in self._job_cache:
            return self._job_cache[job_id]
        
        try:
            raw_job = self.api_client.get_job(job_id)
            if raw_job:
                job = Job.from_api_response(raw_job)
                self._job_cache[job_id] = job
                return job
            return None
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {e}")
            return None
    
    def submit_job(
        self,
        username: str,
        job_name: str,
        script_content: str,
        payload: Dict[str, Any],
        job_options: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Submit a new job.
        
        Args:
            username: Username submitting the job
            job_name: Name of the job
            script_content: User's script content (without SBATCH directives)
            payload: API payload for job submission
            job_options: Optional job options (account, partition, qos, etc.)
        
        Returns:
            Tuple of (success, message, job_id)
        """
        try:
            # 1. Create user directories and paths
            paths = self.file_manager.build_job_paths(username, job_name)
            
            # 2. Build complete SBATCH script with directives
            sbatch_script = self._build_sbatch_script(
                job_name=job_name,
                user_script=script_content,
                output_path=paths['output_loc'],
                error_path=paths['error_loc'],
                job_options=job_options or payload.get('job', {})
            )
            
            # 3. Save the COMPLETE SBATCH script (for traceability)
            self.file_manager.save_script(paths['script_loc'], sbatch_script)
            logger.info(f"Saved complete SBATCH script to {paths['script_loc']}")
            
            # 4. Submit to Slurm API
            response = self.api_client.submit_job(payload)
            
            if response and 'job_id' in response:
                job_id = str(response['job_id'])
                
                # 5. Update local tracking
                self._save_job_metadata(job_id, job_name, paths, job_options)
                
                message = f"Submitted batch job {job_id}"
                logger.info(message)
                return True, message, job_id
            else:
                errors = response.get('errors', ['Unknown error']) if response else ['API request failed']
                error_msg = errors[0] if isinstance(errors, list) else str(errors)
                logger.error(f"Job submission failed: {error_msg}")
                return False, f"Error: {error_msg}", None
        
        except Exception as e:
            error_msg = f"Exception during job submission: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg, None
    
    def _build_sbatch_script(
        self,
        job_name: str,
        user_script: str,
        output_path: str,
        error_path: str,
        job_options: Dict[str, Any]
    ) -> str:
        """
        Build complete SBATCH script with directives.
        This creates a complete, self-contained script that can be re-submitted.
        
        Args:
            job_name: Name of the job
            user_script: User's script content
            output_path: Path for stdout
            error_path: Path for stderr
            job_options: Job configuration (account, partition, qos, etc.)
        
        Returns:
            Complete SBATCH script as string
        """
        lines = [
            "#!/bin/bash",
            "# ========================================",
            "# SLURM Job Script",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# ========================================",
            "",
            f"#SBATCH --job-name={job_name}",
        ]
        
        # Add SBATCH directives from job_options
        if job_options.get('account'):
            lines.append(f"#SBATCH --account={job_options['account']}")
        
        if job_options.get('partition'):
            lines.append(f"#SBATCH --partition={job_options['partition']}")
        
        if job_options.get('qos'):
            lines.append(f"#SBATCH --qos={job_options['qos']}")
        
        # Time limit
        time_limit = job_options.get('time_limit')
        if time_limit:
            if isinstance(time_limit, dict) and time_limit.get('set'):
                lines.append(f"#SBATCH --time={time_limit.get('number', 300)}")
            elif isinstance(time_limit, (int, str)):
                lines.append(f"#SBATCH --time={time_limit}")
        
        # Resources
        if job_options.get('ntasks'):
            lines.append(f"#SBATCH --ntasks={job_options['ntasks']}")
        
        if job_options.get('cpus_per_task'):
            lines.append(f"#SBATCH --cpus-per-task={job_options['cpus_per_task']}")
        
        if job_options.get('nodes'):
            lines.append(f"#SBATCH --nodes={job_options['nodes']}")
        
        if job_options.get('memory'):
            lines.append(f"#SBATCH --mem={job_options['memory']}")
        
        # Output and error files
        lines.append(f"#SBATCH --output={output_path}")
        lines.append(f"#SBATCH --error={error_path}")
        
        # Working directory
        if job_options.get('current_working_directory'):
            lines.append(f"#SBATCH --chdir={job_options['current_working_directory']}")
        
        # Email notifications (if configured)
        if job_options.get('mail_user'):
            lines.append(f"#SBATCH --mail-user={job_options['mail_user']}")
            lines.append(f"#SBATCH --mail-type={job_options.get('mail_type', 'END,FAIL')}")
        
        # Add separator and user script
        lines.extend([
            "",
            "# ========================================",
            "# User Script",
            "# ========================================",
            "",
            user_script.strip()
        ])
        
        return "\n".join(lines) + "\n"
    
    def _save_job_metadata(
        self, 
        job_id: str, 
        job_name: str, 
        paths: Dict[str, str],
        job_options: Optional[Dict[str, Any]] = None
    ):
        """
        Save job metadata to JSON file for tracking.
        
        Args:
            job_id: Job ID from Slurm
            job_name: Name of the job
            paths: Dictionary of file paths
            job_options: Optional job configuration
        """
        try:
            metadata = {
                'job_id': job_id,
                'job_name': job_name,
                'submitted_at': datetime.now().isoformat(),
                'script_path': paths.get('script_loc'),
                'output_path': paths.get('output_loc'),
                'error_path': paths.get('error_loc'),
                'options': job_options or {}
            }
            
            metadata_path = paths.get('jobs_loc', paths.get('script_loc', '').replace('.sh', '.json'))
            
            import json
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.debug(f"Saved job metadata to {metadata_path}")
        
        except Exception as e:
            logger.error(f"Failed to save job metadata: {e}")
    
    def cancel_job(self, job_id: str) -> Tuple[bool, str]:
        """
        Cancel a job.
        
        Args:
            job_id: Job ID to cancel
        
        Returns:
            Tuple of (success, message)
        """
        try:
            success = self.api_client.cancel_job(job_id)
            
            if success:
                message = f"Job {job_id} cancelled successfully"
                # Remove from cache
                self._job_cache.pop(job_id, None)
                return True, message
            else:
                message = f"Failed to cancel job {job_id}"
                return False, message
        
        except Exception as e:
            error_msg = f"Error cancelling job {job_id}: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
    
    def get_job_output(self, job_id: str, tail_lines: int = 1000) -> str:
        """
        Get job output file content.
        
        Args:
            job_id: Job ID
            tail_lines: Number of lines to read from end
        
        Returns:
            Output content or error message
        """
        try:
            job = self.get_job_by_id(job_id)
            if not job or not job.output_path:
                return "Output file not found"
            
            return self.file_manager.read_file_tail(
                job.output_path,
                tail_lines=tail_lines
            )
        except Exception as e:
            return f"Error reading output: {str(e)}"
    
    def get_job_script(self, job_id: str) -> str:
        """
        Get job script content.
        
        Args:
            job_id: Job ID
        
        Returns:
            Script content or error message
        """
        try:
            job = self.get_job_by_id(job_id)
            if not job or not job.script_path:
                return "Script file not found"
            
            return self.file_manager.read_file(job.script_path)
        except Exception as e:
            return f"Error reading script: {str(e)}"
    
    # ===== Cluster Information =====
    
    def get_partitions(self, force_refresh: bool = False) -> List[Partition]:
        """
        Get available partitions.
        
        Args:
            force_refresh: If True, bypass cache
        
        Returns:
            List of Partition objects
        """
        if not force_refresh and self._partitions_cache:
            return self._partitions_cache
        
        try:
            raw_partitions = self.api_client.get_partitions()
            partitions = [Partition.from_api_response(p) for p in raw_partitions]
            self._partitions_cache = partitions
            return partitions
        except Exception as e:
            logger.error(f"Error getting partitions: {e}")
            return []
        
    def get_resources(self) -> List[dict]:
        """
        Build the resources list from slurmrestd v0.0.40:
        - Partition availability from partition.partition.state (contains "UP" if available)
        - Nodes/CPUs computed by intersecting nodes that list this partition in node['partitions']
        
        Returns:
            List of resource dictionaries with partition info
        """
        try:
            raw_partitions = self.api_client.get_partitions() 
            raw_nodes      = self.api_client.get_nodes()      
            
            resources = []
            
            for p in raw_partitions:
                pname = p.get('name', 'unknown')
                
                # Availability/state
                state_list = p.get('partition', {}).get('state', [])
                available = 'up' if 'UP' in state_list else 'down'
                state_flag = state_list[0] if state_list else 'unknown'
                
                # Nodes belonging to this partition: filter by node['partitions']
                part_nodes = [n for n in raw_nodes if pname in (n.get('partitions') or [])]
                node_count = len(part_nodes)
                
                # CPUs
                total_cpus = sum(n.get('cpus', 0) for n in part_nodes)
                     
                # Memory (optional aggregate)
                total_mem = sum(n.get('real_memory', 0) for n in part_nodes)
                
                # Nodes list (compact)
                nodeslist = ",".join([n.get('name', '') for n in part_nodes][:5])
                if node_count > 5:
                    nodeslist += "..."
                
                resources.append({
                    "partition": pname,
                    "available": available,
                    "state": state_flag,
                    "memory": f"{total_mem}" if total_mem else "",
                    "cpus": f"{total_cpus}",
                    "nodeslist": nodeslist,
                    "nodes": node_count,
                })
            
            return resources
        
        except Exception as e:
            logger.exception(f"get_resources failed: {e}")
            return []
        
    def get_stats(self) -> List[dict]:

        try:
            raw_nodes      = self.api_client.get_nodes()
            raw_jobs       = self.api_client.get_cluster_jobs()

            stats = []
            nodes_count = len(raw_nodes)
            total_cores = sum(n.get('cpus', 0) for n in raw_nodes)

            total_jobs = len(raw_jobs)
            running_jobs = sum(1 for j in raw_jobs
                                if (j.get('job_state') or [''])[0] == 'RUNNING')
            stats.append({
                "nodes":nodes_count,
                "cores":total_cores,
                "running_jobs":running_jobs,
                "total_jobs":total_jobs
            })
            
            return stats
    
        except Exception as e:
            logger.exception(f"get_stats failed: {e}")
            return []
    
    def get_qos_list(self, force_refresh: bool = False) -> List[QOS]:
        """
        Get available QOS (Quality of Service) options.
        
        Args:
            force_refresh: If True, bypass cache
        
        Returns:
            List of QOS objects
        """
        if not force_refresh and self._qos_cache:
            return self._qos_cache
        
        try:
            raw_qos = self.api_client.get_qos()
            qos_list = [QOS.from_api_response(q) for q in raw_qos]
            self._qos_cache = qos_list
            return qos_list
        except Exception as e:
            logger.error(f"Error getting QOS: {e}")
            return []
    
    def clear_cache(self):
        """Clear all cached data"""
        self._job_cache.clear()
        self._partitions_cache.clear()
        self._qos_cache.clear()
        logger.info("Job service cache cleared")


# Global service instance
_service: Optional[JobService] = None


def get_job_service() -> JobService:
    """Get or create the global job service instance"""
    global _service
    if _service is None:
        _service = JobService()
    return _service