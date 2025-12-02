# config/settings.py
"""
Centralized configuration management for Slurm Web GUI.
All environment variables and constants are defined here.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class SlurmConfig:
    """Slurm API configuration"""
    url: str
    token: str
    api_version: str
    auth_type: str
    user: str
    
    @classmethod
    def from_env(cls):
        return cls(
            url=os.environ.get('SLURMRESTD_URL', 'http://slurmrestd:6820'),
            token=os.environ.get('SLURMRESTD_TOKEN', ''),
            api_version=os.environ.get('SLURM_API_VERSION', 'v0.0.43'),
            auth_type=os.environ.get('SLURM_AUTH_TYPE', 'none'),
            user=os.environ.get('SLURM_USER', 'slurm'),
        )


@dataclass
class MongoDBConfig:
    """MongoDB configuration"""
    host: str
    port: int
    database: str
    enabled: bool
    
    @classmethod
    def from_env(cls):
        return cls(
            host=os.environ.get('MONGO_HOST', 'mongodb'),
            port=int(os.environ.get('MONGO_PORT', 27017)),
            database=os.environ.get('MONGO_DB_NAME', 'slurm_metrics_db'),
            enabled=os.environ.get('MONGODB_ENABLED', 'true').lower() == 'true'
        )


@dataclass
class PathConfig:
    """File system paths configuration"""
    home: str
    base_user_job_dir: str
    
    @classmethod
    def from_env(cls):
        return cls(
            home=os.environ.get('HOME', '/home/slurm'),
            base_user_job_dir=os.environ.get('BASE_USER_JOB_DIR', '/data/slurm/users')
        )


@dataclass
class MetricsConfig:
    """Metrics polling configuration"""
    polling_interval: int
    
    @classmethod
    def from_env(cls):
        return cls(
            polling_interval=int(os.environ.get('POLLING_INTERVAL_SECONDS', 60))
        )


@dataclass
class NotificationConfig:
    """Job notification settings"""
    failed_enabled: bool
    cancelled_enabled: bool
    timeout_enabled: bool
    completed_enabled: bool
    
    @classmethod
    def from_env(cls):
        return cls(
            failed_enabled=os.environ.get('NOTIFY_FAILED', 'true').lower() == 'true',
            cancelled_enabled=os.environ.get('NOTIFY_CANCELLED', 'true').lower() == 'true',
            timeout_enabled=os.environ.get('NOTIFY_TIMEOUT', 'true').lower() == 'true',
            completed_enabled=os.environ.get('NOTIFY_COMPLETED', 'true').lower() == 'true'
        )


class AppConfig:
    """Main application configuration aggregator"""
    
    def __init__(self):
        self.slurm = SlurmConfig.from_env()
        self.mongodb = MongoDBConfig.from_env()
        self.paths = PathConfig.from_env()
        self.metrics = MetricsConfig.from_env()
        self.notifications = NotificationConfig.from_env()
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.slurm.url:
            return False, "SLURMRESTD_URL is required"
        
        if not self.paths.home:
            return False, "HOME directory is not set"
        
        return True, None


# Global config instance
config = AppConfig()
