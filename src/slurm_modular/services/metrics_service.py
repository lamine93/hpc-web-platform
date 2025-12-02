# services/metrics_service.py
"""
Metrics collection and background thread management.
Separated from main application logic.
"""

import logging
import threading
from typing import Optional

from ..config.settings import config


logger = logging.getLogger(__name__)

# Global thread management
_metrics_thread: Optional[threading.Thread] = None
_thread_stop_event = threading.Event()


def metrics_background_thread(app, socketio):
    """
    Background thread that collects metrics and broadcasts via WebSocket.
    
    Args:
        app: Flask application instance
        socketio: Flask-SocketIO instance
    """
    # Import here to avoid circular dependencies
    from .metrics import get_all_dashboard_metrics
    
    logger.info("Metrics background thread started")
    
    while not _thread_stop_event.is_set():
        try:
            # Create application context for each iteration
            with app.app_context():
                # Collect metrics and broadcast
                get_all_dashboard_metrics(socketio=socketio)
        
        except Exception as e:
            logger.error(f"Error in metrics collection: {e}", exc_info=True)
        
        # Sleep for the configured interval
        socketio.sleep(config.metrics.polling_interval)
    
    logger.info("Metrics background thread stopped")


def start_metrics_thread(app, socketio):
    """
    Start the metrics collection background thread.
    
    Args:
        app: Flask application instance
        socketio: Flask-SocketIO instance
    """
    global _metrics_thread
    
    # Initialize MongoDB connection
    from .metrics import init_mongodb
    init_mongodb()
    
    # Check if thread is already running
    if _metrics_thread is not None and _metrics_thread.is_alive():
        logger.warning("Metrics thread already running")
        return
    
    # Reset stop event
    _thread_stop_event.clear()
    
    # Start the background task
    logger.info("Starting metrics collection thread")
    _metrics_thread = socketio.start_background_task(
        metrics_background_thread,
        app,
        socketio
    )


def stop_metrics_thread():
    """Stop the metrics collection thread gracefully."""
    global _metrics_thread
    
    if _metrics_thread is None or not _metrics_thread.is_alive():
        logger.info("No metrics thread to stop")
        return
    
    logger.info("Stopping metrics thread...")
    _thread_stop_event.set()
    
    # Wait for thread to finish (with timeout)
    _metrics_thread.join(timeout=10)
    
    if _metrics_thread.is_alive():
        logger.warning("Metrics thread did not stop gracefully")
    else:
        logger.info("Metrics thread stopped successfully")
    
    _metrics_thread = None


def is_metrics_thread_running() -> bool:
    """
    Check if metrics thread is currently running.
    
    Returns:
        True if thread is alive, False otherwise
    """
    return _metrics_thread is not None and _metrics_thread.is_alive()
