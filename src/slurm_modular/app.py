# app.py
"""
Main application entry point using the modular architecture.
"""

import logging
import atexit
from flask import Flask
from flask_socketio import SocketIO
from flask_login import LoginManager

# Import from modular structure
from slurm_modular import (
    create_app,
    init_socketio,
    init_services,
    cleanup_services,
    config
)
from slurm_modular.services.metrics_service import start_metrics_thread


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_application():
    """
    Create and configure the complete application with all extensions.
    """
    # Create Flask app
    app = create_app()
    
    # Initialize Socket.IO
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',  # or 'eventlet' / 'gevent'
        logger=True,
        engineio_logger=False
    )
    
    # Register Socket.IO events
    init_socketio(app, socketio)
    
    # Initialize Flask-Login (if you use it)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        # Implement your user loading logic
        # from your_user_module import User
        # return User.get(user_id)
        pass
    
    # Application startup tasks
    with app.app_context():
        # Initialize services
        if not init_services():
            logger.error("Failed to initialize services")
            raise RuntimeError("Service initialization failed")
        
        # Start metrics collection thread (if MongoDB enabled)
        if config.mongodb.enabled:
            start_metrics_thread(app, socketio)
            logger.info("Metrics collection thread started")
    
    # Register cleanup on shutdown
    atexit.register(cleanup_services)
    
    logger.info("Application created and configured successfully")
    return app, socketio


# Create the application
app, socketio = create_application()


if __name__ == '__main__':
    # Run the application
    logger.info(f"Starting Slurm Web GUI on port 5000")
    logger.info(f"Slurm API: {config.slurm.url}")
    logger.info(f"MongoDB enabled: {config.mongodb.enabled}")
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False,  # Set to True for development
        use_reloader=False  # Disable reloader to prevent double initialization
    )
