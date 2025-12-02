# file_browser.py
import os
import time
from flask import Blueprint, jsonify, render_template, request, abort, current_app, send_file

from flask_login import login_required, current_user

# Define the Blueprint
bp = Blueprint('files', __name__)

# --- UTILITY AND SECURITY FUNCTIONS ---

def get_user_base_path(username):
    """Retrieves the user's secure base directory path on the cluster filesystem."""
    # Retrieves the base path configured in the Flask application
    base_dir = current_app.config.get('CLUSTER_WORK_DIR', '/scratch')
    return os.path.join(base_dir, username)

def secure_path_check(requested_path, username):
    """
    Checks if the requested path is safely contained within the user's base directory.
    Prevents path traversal attacks (e.g., requests like '../../../etc/passwd').
    """
    BASE_PATH = get_user_base_path(username)
    
    # 1. Join the base path and the requested path, then normalize it (resolves '.', '..').
    # The lstrip('/') prevents paths like '/../../etc/passwd' being treated as relative to root.
    full_requested_path = os.path.join(BASE_PATH, requested_path.lstrip('/'))
    absolute_path = os.path.abspath(full_requested_path)
    
    # 2. Path Traversal Check: The resolved absolute path MUST start with the user's BASE_PATH.
    if not absolute_path.startswith(BASE_PATH):
        # User is trying to exit their allowed directory
        abort(403, description="Path traversal attempt detected.") 
    
    return absolute_path

# --- API ROUTES ---

@bp.route('/api/file_browser/list', methods=['GET'])
@login_required
def list_directory_contents():
    # Get the requested path from the query parameters (defaults to empty/root if not provided)
    requested_path = request.args.get('path', '') 
    
    try:
        # CRUCIAL security check
        secure_full_path = secure_path_check(requested_path, current_user.username)
        
        # Logic to list contents
        contents = []
        with os.scandir(secure_full_path) as entries:
            for entry in entries:
                stats = entry.stat()
                
                # Basic size formatting (in KB)
                size_kb = round(stats.st_size / 1024, 2)
                
                contents.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": f"{size_kb} KB" if entry.is_file() else "-",
                    "modified_timestamp": stats.st_mtime,
                     # Format timestamp to human-readable date
                    "modified_date": time.strftime('%Y-%m-%d %H:%M', time.localtime(stats.st_mtime))
                })
        
        # Sort contents: directories first, then alphabetically by name
        contents.sort(key=lambda x: (x['type'] != 'dir', x['name'].lower()))

        return jsonify({"current_path": requested_path, "contents": contents})
        
    except FileNotFoundError:
        return jsonify({"error": "Directory not found."}), 404
    except PermissionError:
        return jsonify({"error": "Permission denied."}), 403
    except Exception as e:
        # Catch unexpected errors during file system operations
        return jsonify({"error": f"Internal error: {e}"}), 500


@bp.route('/api/file_browser/download', methods=['GET'])
@login_required
def download_file():
    filepath = request.args.get('filepath')
    
    if not filepath:
        return jsonify({"error": "Missing filepath parameter."}), 400

    try:
        # CRUCIAL security check
        secure_full_path = secure_path_check(filepath, current_user.username)
        
        if os.path.isdir(secure_full_path):
            return jsonify({"error": "Cannot download a directory."}), 400
        
        if not os.path.exists(secure_full_path):
             return jsonify({"error": "File not found."}), 404

        # Use Flask's send_file to stream the file securely
        return send_file(
            secure_full_path, 
            as_attachment=True, # Forces browser to download instead of display
            download_name=os.path.basename(secure_full_path) # Sets the filename for the user
        )
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@bp.route('/api/file_browser/delete', methods=['POST'])
@login_required
def delete_files():
    """Deletes a list of files requested by the user, after security check."""
    
    data = request.get_json()
    files_to_delete = data.get('files', [])

    if not files_to_delete or not isinstance(files_to_delete, list):
        abort(400, description="Invalid list of files provided.")
    
    username = current_user.username
    deleted_count = 0
    errors = []

    for filename in files_to_delete:
        try:
            absolute_path = secure_path_check(filename, username)
            
            if not os.path.exists(absolute_path):
                errors.append(f"File not found: {filename}")
                continue
            if not os.path.isfile(absolute_path):
                errors.append(f"Not a file, skipping: {filename}")
                continue

            os.remove(absolute_path)
            deleted_count += 1
            
        except Exception as e:
            errors.append(f"Failed to delete {filename}: {e}")
            
    if errors:
        return jsonify({
            'message': f"{deleted_count} files deleted, but encountered errors.",
            'errors': errors
        }), 400 if deleted_count == 0 else 200 

    return jsonify({'message': f'{deleted_count} files successfully deleted.'}), 200



@bp.route('/files')
@login_required
def file_explorer():
    absolute_work_path = get_user_base_path(current_user.username)
    return render_template('files_browser/file_browser.html', display_path=absolute_work_path)
