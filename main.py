# main.py - Entry point with slurm_modular integration using config.json

import json
import os
from flask import Flask
from flask_socketio import SocketIO
from flask_login import LoginManager
from flask import session,redirect,render_template,url_for
from flask_login import login_required, current_user

# Load configuration from config.json
def load_config():
    """Load configuration from config.json file"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

# Load config
config = load_config()

# Import existing blueprints (your current modules)
from src.auth import bp as auth_bp
from src.file_browser import bp as files_bp
#from src.posts import bp as posts_bp

# Import slurm_modular components
from src.slurm_modular.routes.slurm_routes import bp as slurm_bp, register_socketio_events
from src.slurm_modular.services.metrics_service import start_metrics_thread


def create_app():
    """Application factory pattern"""
    
    app = Flask(__name__,
                template_folder='src/templates',
                static_folder='src/static')
    
    # Configuration from config.json
    app.config['SECRET_KEY'] = config.get('SECRET_KEY')
    
    # LDAP configuration (for your auth module)
    app.config['LDAP_URI'] = config.get('LDAP_URI')
    app.config['LDAP_BASE_DN'] = config.get('LDAP_BASE_DN')
    app.config['LDAP_BIND_DN'] = config.get('LDAP_BIND_DN')
    app.config['LDAP_BIND_PASSWORD'] = config.get('LDAP_BIND_PASSWORD')
    app.config['LDAP_USER_FILTER'] = config.get('LDAP_USER_FILTER')
    app.config['LDAP_REQUIRE_GROUP_DN'] = config.get('LDAP_REQUIRE_GROUP_DN')
    app.config['LDAP_START_TLS'] = config.get('LDAP_START_TLS', False)
    app.config['ENABLE_LOCAL_FALLBACK'] = config.get('ENABLE_LOCAL_FALLBACK', True)
    app.config['LOCAL_ADMIN_USERNAME'] = config.get('LOCAL_ADMIN_USERNAME')
    app.config['LOCAL_ADMIN_PASSWORD_HASH'] = config.get('LOCAL_ADMIN_PASSWORD_HASH')
    
    # Slurm configuration
    app.config['SLURM_API_URL'] = config.get('SLURMRESTD_URL', 'http://slurmrestd:6820')
    app.config['SLURM_API_VERSION'] = config.get('SLURMRESTD_API_VERSION', 'v0.0.40')
    
    # Optional: Slurm API token (if you use JWT authentication)
    app.config['SLURM_API_TOKEN'] = config.get('SLURM_JWT_FILE', '/tokens/slurm.jwt')
    
    # Prometheus configuration (optional)
    app.config['PROMETHEUS_URL'] = config.get('PROMETHEUS_URL', 'http://prometheus:9090')
    
    # MongoDB configuration (optional - for metrics storage)
    app.config['MONGODB_ENABLED'] = config.get('MONGODB_ENABLED', True)
    app.config['MONGODB_URI'] = config.get('MONGODB_URI', 'mongodb://mongodb:27017')
    app.config['MONGODB_DATABASE'] = config.get('MONGODB_DATABASE', 'slurm_metrics')
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        # Import here to avoid circular imports
        from src.auth import get_user_by_id
        return get_user_by_id(user_id)
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    #app.register_blueprint(posts_bp, url_prefix='/posts')
    app.register_blueprint(slurm_bp, url_prefix='/slurm')
    app.register_blueprint(files_bp, url_prefix='/files')
    
    return app


# Create app instance
app = create_app()

# Initialize SocketIO
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   ping_interval=180,
                   ping_timeout=300,
                   logger=True,
                   engineio_logger=True)

# Register Slurm WebSocket events
register_socketio_events(socketio)

# Start metrics collection thread
with app.app_context():
    start_metrics_thread(app, socketio)

@app.route('/')
def index():
    """Root redirect"""
    from flask import redirect, url_for
    from flask_login import current_user
    
    if current_user.is_authenticated:
        return redirect(url_for('slurm.dashboard'))
    else:
        return redirect(url_for('auth.login'))


if __name__ == '__main__':
    port = config.get('port', 5000)
    socketio.run(app, 
                host="0.0.0.0", 
                debug=True, 
                port=port, 
                allow_unsafe_werkzeug=True, 
                use_reloader=False)
    
