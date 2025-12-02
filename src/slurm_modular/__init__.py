# __init__.py
"""
Slurm Web GUI - Modular Architecture

Main module initialization. Provides factory functions for creating
Flask app with all components properly configured.
"""

import logging
from flask import Flask
from flask_socketio import SocketIO

from .config.settings import config
from .routes.slurm_routes import bp as slurm_bp, register_socketio_events
from .services.job_service import get_job_service
from .services.notification_service import get_notification_service


logger = logging.getLogger(__name__)


def create_app(config_override=None):
    """
    Application factory for creating Flask app.
    
    Args:
        config_override: Optional dict to override configuration
    
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config)
    if config_override:
        app.config.update(config_override)
    
    # Validate configuration
    is_valid, error = config.validate()
    if not is_valid:
        raise ValueError(f"Invalid configuration: {error}")
    
    # Register blueprints
    app.register_blueprint(slurm_bp)
    
    logger.info("Flask application created successfully")
    return app


def init_socketio(app, socketio):
    """
    Initialize Socket.IO with the application.
    
    Args:
        app: Flask application
        socketio: Flask-SocketIO instance
    
    Returns:
        Configured SocketIO instance
    """
    # Register Socket.IO event handlers
    register_socketio_events(socketio)
    
    # Initialize notification service with socketio
    notification_service = get_notification_service(socketio)
    
    logger.info("Socket.IO initialized successfully")
    return socketio


def init_services():
    """
    Initialize all services.
    Call this on application startup.
    """
    try:
        # Initialize job service (lazy loads API client)
        job_service = get_job_service()
        logger.info("Job service initialized")
        
        # Initialize notification service
        notification_service = get_notification_service()
        logger.info("Notification service initialized")
        
        # Pre-cache partitions and QOS
        job_service.get_partitions()
        job_service.get_qos_list()
        
        logger.info("All services initialized successfully")
        return True
    
    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        return False


def cleanup_services():
    """
    Cleanup all services on application shutdown.
    """
    try:
        from .api.slurm_client import get_client
        
        # Close API client
        client = get_client()
        client.close()
        
        logger.info("Services cleaned up successfully")
    
    except Exception as e:
        logger.error(f"Error cleaning up services: {e}")


__all__ = [
    'create_app',
    'init_socketio',
    'init_services',
    'cleanup_services',
    'config'
]
