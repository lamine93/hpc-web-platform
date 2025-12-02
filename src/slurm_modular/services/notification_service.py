# services/notification_service.py
"""
Job state change notification system.
"""

import logging
from typing import Dict, Optional, Set
from datetime import datetime

from ..models.job import Job, JobState
from ..config.settings import config


logger = logging.getLogger(__name__)


class NotificationService:
    """
    Monitors job state changes and triggers notifications.
    """
    
    def __init__(self, socketio=None):
        self.socketio = socketio
        self.previous_states: Dict[str, JobState] = {}
        self.notified_jobs: Set[str] = set()
        
        # Notification settings from config
        self.settings = {
            JobState.FAILED: config.notifications.failed_enabled,
            JobState.CANCELLED: config.notifications.cancelled_enabled,
            JobState.TIMEOUT: config.notifications.timeout_enabled,
            JobState.COMPLETED: config.notifications.completed_enabled
        }
    
    def check_and_notify(self, jobs: list[Job], room: Optional[str] = None):
        """
        Check for job state changes and send notifications.
        
        Args:
            jobs: List of Job objects
            room: Optional Socket.IO room to send notifications to
        """
        for job in jobs:
            self._process_job(job, room)
    
    def _process_job(self, job: Job, room: Optional[str] = None):
        """Process a single job for state changes"""
        job_id = job.job_id
        current_state = job.state
        
        if not job_id or not current_state:
            return
        
        # Get previous state
        previous_state = self.previous_states.get(job_id)
        
        # Check if this is a state change
        if previous_state and previous_state != current_state:
            # Check if we should notify for this state
            if current_state in self.settings and self.settings[current_state]:
                # Prevent duplicate notifications
                notification_key = f"{job_id}:{current_state.value}"
                if notification_key not in self.notified_jobs:
                    self._send_notification(job, previous_state, room)
                    self.notified_jobs.add(notification_key)
        
        # Update state tracking
        self.previous_states[job_id] = current_state
        
        # Clean up notified_jobs set if job is terminal
        if job.is_terminal_state():
            # Keep track for a while, but clean up eventually
            # Could add a timestamp-based cleanup here
            pass
    
    def _send_notification(self, job: Job, previous_state: JobState, room: Optional[str] = None):
        """
        Send notification via Socket.IO.
        
        Args:
            job: Job object
            previous_state: Previous job state
            room: Optional Socket.IO room
        """
        if not self.socketio:
            logger.warning("Socket.IO not configured for notifications")
            return
        
        notification = {
            'type': job.state.value,
            'job_id': job.job_id,
            'job_name': job.name,
            'previous_state': previous_state.value,
            'current_state': job.state.value,
            'user': job.user,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if room:
                self.socketio.emit('new_job_notification', notification, room=room)
            else:
                self.socketio.emit('new_job_notification', notification, broadcast=True)
            
            logger.info(f"Notification sent: Job {job.job_id} {previous_state.value} -> {job.state.value}")
        
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def update_settings(self, state: JobState, enabled: bool):
        """
        Update notification settings for a specific state.
        
        Args:
            state: Job state
            enabled: Whether notifications are enabled
        """
        if state in self.settings:
            self.settings[state] = enabled
            logger.info(f"Notification for {state.value} set to {enabled}")
    
    def clear_history(self, job_id: Optional[str] = None):
        """
        Clear notification history.
        
        Args:
            job_id: If provided, clear only for this job. Otherwise clear all.
        """
        if job_id:
            self.previous_states.pop(job_id, None)
            # Remove all notifications for this job
            self.notified_jobs = {
                key for key in self.notified_jobs 
                if not key.startswith(f"{job_id}:")
            }
        else:
            self.previous_states.clear()
            self.notified_jobs.clear()
        
        logger.info(f"Notification history cleared{' for job ' + job_id if job_id else ''}")
    
    def get_stats(self) -> Dict:
        """
        Get notification statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            'tracked_jobs': len(self.previous_states),
            'notifications_sent': len(self.notified_jobs),
            'settings': {
                state.value: enabled 
                for state, enabled in self.settings.items()
            }
        }


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service(socketio=None) -> NotificationService:
    """
    Get or create the global notification service.
    
    Args:
        socketio: Flask-SocketIO instance
    
    Returns:
        NotificationService instance
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(socketio)
    elif socketio and not _notification_service.socketio:
        _notification_service.socketio = socketio
    return _notification_service
