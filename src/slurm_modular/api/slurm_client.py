# api/slurm_client.py
"""
Slurm REST API client with proper error handling and retry logic.
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..utils.helpers import get_jwt
from ..config.settings import config


logger = logging.getLogger(__name__)


class SlurmAPIError(Exception):
    """Custom exception for Slurm API errors"""
    pass


class SlurmAPIClient:
    """
    Thread-safe Slurm REST API client.
    Handles authentication, retries, and error handling.
    """
    
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or config.slurm.url
        self.token = get_jwt() or config.slurm.token
        self.api_version = config.slurm.api_version
        self.auth_type = config.slurm.auth_type
        self.user = config.slurm.user
        
        # Configure session with connection pooling and retries
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-SLURM-USER-NAME': self.user
        }
        if self.auth_type == 'jwt' and self.token:
            headers['X-SLURM-USER-TOKEN'] = self.token
        
        return headers
    
    def _request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Slurm API.
        
        Args:
            endpoint: API endpoint (e.g., 'slurm/v0.0.43/jobs')
            method: HTTP method
            data: Request payload for POST/PUT
            timeout: Request timeout in seconds
        
        Returns:
            API response as dictionary, or None on error
        
        Raises:
            SlurmAPIError: On API errors
        """
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()
        
        try:
            logger.debug(f"Slurm API {method} request: {url}")
            
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=timeout
            )
            
            # Log response for debugging
            logger.debug(f"Slurm API response status: {response.status_code}")
            
            # Handle different status codes
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Resource not found: {url}")
                return None
            elif response.status_code >= 400:
                error_msg = f"API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise SlurmAPIError(error_msg)
            
            return response.json()
        
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to Slurm API: {url}")
            raise SlurmAPIError(f"Timeout connecting to {url}")
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Slurm API: {e}")
            raise SlurmAPIError(f"Connection error: {str(e)}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise SlurmAPIError(f"Request failed: {str(e)}")
        
        except Exception as e:
            logger.exception(f"Unexpected error in API request: {e}")
            raise SlurmAPIError(f"Unexpected error: {str(e)}")
    
    # ===== Job Management =====
    
    def get_jobs(self, start_time: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all jobs, optionally filtered by user.
        
        Args:
            user: Optional username to filter jobs
        
        Returns:
            List of job dictionaries
        """
        params = {}
        if start_time is None:
            start_time = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
            params["start_time"] = f"{start_time}"

        if start_time is not None:
            params["start_time"] = f"{start_time}"

        
        endpoint = f"slurmdb/{self.api_version}/jobs"
        
        try:
            response = self._request(endpoint=endpoint, params=params)
            return response.get('jobs', []) if response else []
        except SlurmAPIError as e:
            logger.error(f"Failed to get jobs: {e}")
            return []
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific job.
        
        Args:
            job_id: Job ID
        
        Returns:
            Job dictionary or None
        """
        endpoint = f"slurmdb/{self.api_version}/job/{job_id}"
        
        try:
            response = self._request(endpoint)
            if response and 'jobs' in response and response['jobs']:
                return response['jobs'][0]
            return None
        except SlurmAPIError as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None
        
    def get_cluster_jobs(self) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific job.
        
        Args:
            job_id: Job ID
        
        Returns:
            Job dictionary or None
        """
        endpoint = f"slurm/{self.api_version}/jobs"
        
        try:
            response = self._request(endpoint=endpoint)
            return response.get('jobs', []) if response else []
        except SlurmAPIError as e:
            logger.error(f"Failed to get cluster jobs: {e}")
            return []
    
    def submit_job(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Submit a new job.
        
        Args:
            payload: Job submission payload
        
        Returns:
            Response with job_id or None on error
        """
        endpoint = f"slurm/{self.api_version}/job/submit"
        
        try:
            response = self._request(endpoint, method='POST', data=payload)
            if response and 'job_id' in response:
                logger.info(f"Job submitted successfully: {response['job_id']}")
                return response
            else:
                logger.error(f"Job submission failed: {response}")
                return None
        except SlurmAPIError as e:
            logger.error(f"Failed to submit job: {e}")
            return None
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: Job ID to cancel
        
        Returns:
            True if successful, False otherwise
        """
        endpoint = f"slurm/{self.api_version}/job/{job_id}"
        
        try:
            response = self._request(endpoint, method='DELETE')
            if response is not None:
                logger.info(f"Job {job_id} cancelled successfully")
                return True
            return False
        except SlurmAPIError as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    # ===== Cluster Information =====
    
    def get_partitions(self) -> List[Dict[str, Any]]:
        """Get list of partitions"""
        endpoint = f"slurm/{self.api_version}/partitions"
        
        try:
            response = self._request(endpoint)
            return response.get('partitions', []) if response else []
        except SlurmAPIError as e:
            logger.error(f"Failed to get partitions: {e}")
            return []
    
    def get_qos(self) -> List[Dict[str, Any]]:
        """Get list of QOS (Quality of Service)"""
        endpoint = f"slurmdb/{self.api_version}/qos"
        
        try:
            response = self._request(endpoint)
            return response.get('qos', []) if response else []
        except SlurmAPIError as e:
            logger.error(f"Failed to get QOS: {e}")
            return []
    
    def get_nodes(self) -> List[Dict[str, Any]]:
        """Get list of nodes"""
        endpoint = f"slurm/{self.api_version}/nodes"
        
        try:
            response = self._request(endpoint)
            return response.get('nodes', []) if response else []
        except SlurmAPIError as e:
            logger.error(f"Failed to get nodes: {e}")
            return []
    
    def close(self):
        """Close the session"""
        if self.session:
            self.session.close()


# Global client instance (lazy initialized)
_client: Optional[SlurmAPIClient] = None


def get_client() -> SlurmAPIClient:
    """
    Get or create the global Slurm API client.
    Thread-safe singleton pattern.
    """
    global _client
    if _client is None:
        _client = SlurmAPIClient()
    return _client
