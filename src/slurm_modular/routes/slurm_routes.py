# routes/slurm_routes.py
"""
Flask routes for Slurm job management - WebSocket only version.
All interactions via Socket.IO events.
"""

from flask import Blueprint, render_template, request,redirect, url_for
from flask_login import login_required, current_user
from flask_socketio import emit, join_room
import logging
from datetime import datetime, timedelta, timezone


from ..services.job_service import get_job_service
from ..services.notification_service import get_notification_service
from ..config.settings import config


logger = logging.getLogger(__name__)

# Create Blueprint (only for web pages, no API routes)
bp = Blueprint('slurm', __name__, url_prefix='/slurm')


# ===== Web Pages =====

@bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard/dashboard.html')


@bp.route('/')
def home():
    """Home page - redirects to dashboard or login"""
    if current_user.is_authenticated:
        return redirect(url_for('slurm.dashboard'))
    else:
        return redirect(url_for('auth.login'))


@bp.route('/submit')
@login_required
def submit():
    """Submit job page"""
    job_service = get_job_service()
    
    # Get partitions
    partitions_list = job_service.get_partitions()
    #available_partitions = [p.name for p in partitions_list] if partitions_list else []
    available_partitions =  [ {"name": p.name } for p in partitions_list ]
    # Get QOS
    qos_list = job_service.get_qos_list()
    #available_qoses = [q.name for q in qos_list] if qos_list else []

    available_qoses = [ { "name": qos.name, "default_time_minutes": qos.max_wall_duration_minutes} for qos in qos_list ]

    return render_template('submit/submit.html', 
                         partitions=available_partitions, 
                         qoses=available_qoses)

@bp.route('/resources')
@login_required
def resources():
    """Resources monitoring page"""
    return render_template('resources/resources.html')


@bp.route('/jobs')
@login_required
def jobs():
    """Jobs listing page"""
    try:
        job_service = get_job_service()
        
        # Get QOS names
        qos_list = job_service.get_qos_list()
        qos = [q.name for q in qos_list]
        
        # Get partition names
        partitions_list = job_service.get_partitions()
        partitions = [p.name for p in partitions_list]
        
        return render_template('jobs/jobs.html', 
                             available_partitions=partitions, 
                             available_qos=qos)
    except Exception as e:
        logger.error(f"Error loading jobs page: {e}")
        return render_template('error.html', error=str(e)), 500


@bp.route('/account')
@login_required
def account():
    """User account page"""
    return render_template('account/account.html')


@bp.route('/settings')
@login_required
def settings():
    """Settings page"""
    try:
        job_service = get_job_service()
        
        # Get QOS names
        qos_list = job_service.get_qos_list()
        qos_names = [q.name for q in qos_list]
        
        # Get partition names
        partitions_list = job_service.get_partitions()
        partition_names = [p.name for p in partitions_list]
        
        # Get Slurm version (if available in config)
        slurm_version = getattr(config.slurm, 'version', 'Unknown')
        
        return render_template('settings/settings.html',
                             available_partitions=partition_names,
                             available_qoses=qos_names,
                             slurm_version=slurm_version)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return render_template('error.html', error=str(e)), 500


@bp.route('/job/details/<int:job_id>', endpoint='job_details_page')
@login_required
def job_details_page(job_id):
    """Job details page"""
    try:
        job_service = get_job_service()
        job = job_service.get_job_by_id(str(job_id), force_refresh=True)

        logger.info(f"========job========== {job.to_dict()}")
        
        if not job:
            from flask import abort
            abort(404)
        
        return render_template('jobs/job_details.html', job=job.to_dict())
    except Exception as e:
        logger.error(f"Error loading job details {job_id}: {e}")
        return render_template('error.html', error=str(e)), 500


# ===== Socket.IO Events (ALL operations via WebSocket) =====

def register_socketio_events(socketio):
    """
    Register ALL Socket.IO event handlers.
    Call this from your main app initialization.
    """
    
    # ===== Connection Management =====
    
    @socketio.on('connect')
    def handle_connect():
        """Client connected"""
        logger.info(f"Client {request.sid} connected")
        emit('connected', {'status': 'ok', 'sid': request.sid})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Client disconnected"""
        logger.info(f"Client {request.sid} disconnected")
    
    @socketio.on('join_slurm_room')
    def handle_join_slurm():
        """Join the Slurm room for real-time updates"""
        join_room('slurm')
        logger.debug(f"Client {request.sid} joined Slurm room")
        emit('joined', {'room': 'slurm'})
    
    
    # ===== Job Operations =====
    
    @socketio.on('get_jobs')
    def handle_get_jobs(data=None):
        """Get all jobs for current user"""
        try:
            user_filter = data.get('user') if data else None
            start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
            

            if not user_filter and hasattr(current_user, 'username'):
                user_filter = current_user.username
            
            job_service = get_job_service()
            jobs = job_service.get_all_jobs(start_time=start_time)
            
            emit('jobs_list', {
                'success': True,
                'jobs': [job.to_dict() for job in jobs],
                'count': len(jobs)
            })
        
        except Exception as e:
            logger.error(f"Error getting jobs: {e}")
            emit('error', {'message': f'Error getting jobs: {str(e)}'})
    
    
    @socketio.on('get_job')
    def handle_get_job(data):
        """Get specific job details"""
        try:
            job_id = data.get('job_id')
            if not job_id:
                emit('error', {'message': 'Job ID required'})
                return
            
            job_service = get_job_service()
            job = job_service.get_job_by_id(job_id, force_refresh=True)
            
            if job:
                emit('job_details', {
                    'success': True,
                    'job': job.to_dict()
                })
            else:
                emit('job_details', {
                    'success': False,
                    'error': 'Job not found'
                })
        
        except Exception as e:
            logger.error(f"Error getting job: {e}")
            emit('error', {'message': str(e)})
    
    
    @socketio.on('submit_job')
    def handle_submit_job(data):
        """Submit a new job"""
        try:
            # Extract required fields
            job_name = data.get('name')
            script_content = data.get('script')
            
            if not job_name or not script_content:
                emit('submit_result', {
                    'success': False,
                    'error': 'Job name and script are required'
                })
                return
            
            # Get username
            username = data.get('username')
            if not username and hasattr(current_user, 'username'):
                username = current_user.username
            
            if not username:
                emit('submit_result', {
                    'success': False,
                    'error': 'Username required'
                })
                return
            
            # Build API payload
            job_options = data.get('job', {})
            payload = {
                'job': job_options,
                'script': script_content
            }
            
            # Submit job (will save complete SBATCH script with directives)
            job_service = get_job_service()
            success, message, job_id = job_service.submit_job(
                username=username,
                job_name=job_name,
                script_content=script_content,
                payload=payload,
                job_options=job_options  # Pass options to build SBATCH script
            )
            
            emit('submit_result', {
                'success': success,
                'message': message,
                'job_id': job_id
            })
            
            # Broadcast to all clients in the room
            if success:
                socketio.emit('job_submitted', {
                    'job_id': job_id,
                    'job_name': job_name,
                    'user': username
                }, room='slurm')
        
        except Exception as e:
            logger.error(f"Error submitting job: {e}")
            emit('submit_result', {
                'success': False,
                'error': str(e)
            })
    
    
    @socketio.on('cancel_job')
    def handle_cancel_job(data):
        """Cancel a job"""
        try:
            job_id = data.get('job_id')
            if not job_id:
                emit('error', {'message': 'Job ID required'})
                return
            
            job_service = get_job_service()
            success, message = job_service.cancel_job(job_id)
            
            emit('cancel_result', {
                'success': success,
                'message': message,
                'job_id': job_id
            })
            
            # Broadcast to all clients
            if success:
                socketio.emit('job_cancelled', {
                    'job_id': job_id
                }, room='slurm')
        
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            emit('cancel_result', {
                'success': False,
                'error': str(e)
            })
    
    
    @socketio.on('get_job_output')
    def handle_get_job_output(data):
        """Get job output file"""
        try:
            job_id = data.get('job_id')
            if not job_id:
                emit('error', {'message': 'Job ID required'})
                return
            
            tail_lines = data.get('tail_lines', 1000)
            
            job_service = get_job_service()
            output = job_service.get_job_output(job_id, tail_lines=tail_lines)
            
            emit('job_output', {
                'success': True,
                'job_id': job_id,
                'output': output
            })
        
        except Exception as e:
            logger.error(f"Error getting job output: {e}")
            emit('error', {'message': str(e)})
    
    
    @socketio.on('get_job_script')
    def handle_get_job_script(data):
        """Get job script"""
        try:
            job_id = data.get('job_id')
            if not job_id:
                emit('error', {'message': 'Job ID required'})
                return
            
            job_service = get_job_service()
            script = job_service.get_job_script(job_id)
            
            emit('job_script', {
                'success': True,
                'job_id': job_id,
                'script': script
            })
        
        except Exception as e:
            logger.error(f"Error getting job script: {e}")
            emit('error', {'message': str(e)})
    
    
    # ===== Cluster Information =====
    
    @socketio.on('get_partitions')
    def handle_get_partitions():
        """Get available partitions"""
        try:
            job_service = get_job_service()
            partitions = job_service.get_partitions()
            
            emit('partitions_list', {
                'success': True,
                'partitions': [p.__dict__ for p in partitions]
            })
        
        except Exception as e:
            logger.error(f"Error getting partitions: {e}")
            emit('error', {'message': str(e)})
    
    
    @socketio.on('get_qos')
    def handle_get_qos():
        """Get available QOS options"""
        try:
            job_service = get_job_service()
            qos_list = job_service.get_qos_list()
            
            emit('qos_list', {
                'success': True,
                'qos': [q.__dict__ for q in qos_list]
            })
        
        except Exception as e:
            logger.error(f"Error getting QOS: {e}")
            emit('error', {'message': str(e)})
    
    @socketio.on('get_resources')
    def handle_get_resources():
        """Get cluster resources and emit the list of partitions/nodes."""
        try:
            job_service = get_job_service()           
            resources_list = job_service.get_resources()
            
            emit('resources_list', {
                'success': True,
                'resources': resources_list 
            })           
            
        except Exception as e:
            logger.error(f"Error getting resources: {e}")
            emit('error', {'message': str(e)})
    

    @socketio.on('get_stats')
    def handle_get_stats():
        """Get cluster stats and emit the stats."""
        try:
            job_service = get_job_service()
            stats_list = job_service.get_stats()
            emit('stats_list', {
                'success': True,
                'stats': stats_list 
            })
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            emit('error', {'message': str(e)})


    # ===== Metrics History =====
    
    @socketio.on('get_metrics_history')
    def handle_get_metrics_history(data=None):
        """Get metrics history from MongoDB"""
        try:
            from ..services.metrics import get_metrics_history_from_db
            
            hours = data.get('hours', 24) if data else 24
            downsample = data.get('downsample_minutes', 5) if data else 5
            
            metrics_list, error = get_metrics_history_from_db(
                hours=hours,
                downsample_minutes=downsample
            )
            
            if error:
                emit('metrics_history', {
                    'success': False,
                    'error': error
                })
            else:
                emit('metrics_history', {
                    'success': True,
                    'data': metrics_list,
                    'hours': hours
                })
        
        except Exception as e:
            logger.error(f"Error getting metrics history: {e}")
            emit('error', {'message': str(e)})
    
    
    @socketio.on('get_metrics_statistics')
    def handle_get_metrics_stats(data=None):
        """Get metrics statistics"""
        try:
            from ..services.metrics import get_metrics_statistics
            
            hours = data.get('hours', 24) if data else 24
            
            stats, error = get_metrics_statistics(hours=hours)
            
            if error:
                emit('metrics_statistics', {
                    'success': False,
                    'error': error
                })
            else:
                emit('metrics_statistics', {
                    'success': True,
                    'statistics': stats,
                    'hours': hours
                })
        
        except Exception as e:
            logger.error(f"Error getting metrics statistics: {e}")
            emit('error', {'message': str(e)})
    
    
    # ===== Real-time Updates (kept for backward compatibility) =====
    
    @socketio.on('request_job_update')
    def handle_job_update_request(data):
        """Handle request for job update (alias for get_job)"""
        handle_get_job(data)
