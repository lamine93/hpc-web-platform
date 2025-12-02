from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from flask_login import LoginManager, login_user, logout_user, UserMixin, login_required
from werkzeug.security import check_password_hash
from ldap3 import Server, Connection, ALL, SUBTREE, Tls, SIMPLE
import ssl
import time

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
bp = auth_bp



class User(UserMixin):
    def __init__(self, uid, cn=None, mail=None, groups=None, is_admin=False, source="ldap"):
        self.id = uid
        self.cn = cn or uid
        self.mail = mail or f"{uid}@local"
        self.is_admin = is_admin
        self.source = source
        self.groups = groups
        
    @property
    def username(self):
        return self.cn


def get_user_by_id(user_id):
    """Load user by ID for Flask-Login"""
    return User(user_id)


_failed_attempts = {}  # key = remote_addr:username, value = (count, first_ts)

def _too_many_attempts(username):
    max_attempts = int(current_app.config.get('MAX_LOGIN_ATTEMPTS', 5))
    key = f"{request.remote_addr}:{username}"
    count, first_ts = _failed_attempts.get(key, (0, time.time()))
    if count >= max_attempts:
        # fenêtre glissante 10 minutes
        if time.time() - first_ts < 600:
            return True
        else:
            _failed_attempts.pop(key, None)
    return False

def _register_failed_attempt(username):
    key = f"{request.remote_addr}:{username}"
    count, first_ts = _failed_attempts.get(key, (0, time.time()))
    _failed_attempts[key] = (count + 1, first_ts)

def _reset_attempts(username):
    key = f"{request.remote_addr}:{username}"
    _failed_attempts.pop(key, None)

# --- LDAP ---
def _ldap_server():
    uri = current_app.config.get('LDAP_URI', 'ldap://localhost:389')
    start_tls = bool(current_app.config.get('LDAP_START_TLS', False))
    server = Server(uri, get_info=ALL)
    tls = Tls(validate=ssl.CERT_NONE) if start_tls else None
    return server, tls

def ldap_authenticate(username, password):
    """
    AuthN LDAP classique :
      1) bind technique (bind_dn/bind_pw)
      2) search user by filter
      3) optional: verify group membership
      4) bind as user with supplied password
    """
    base_dn   = current_app.config.get('LDAP_BASE_DN')
    bind_dn   = current_app.config.get('LDAP_BIND_DN')
    bind_pw   = current_app.config.get('LDAP_BIND_PASSWORD')
    user_filt = current_app.config.get('LDAP_USER_FILTER', '(uid={username})').format(username=username)
    require_group = current_app.config.get('LDAP_REQUIRE_GROUP_DN')

    if not all([base_dn, bind_dn, bind_pw]):
        current_app.logger.error("LDAP config incomplete")
        return None

    server, tls = _ldap_server()

    # 1) bind technique
    try:
        if tls:
            conn = Connection(server, user=bind_dn, password=bind_pw, auto_bind=True, authentication=SIMPLE, read_only=True, tls=tls)
        else:
            conn = Connection(server, user=bind_dn, password=bind_pw, auto_bind=True, authentication=SIMPLE, read_only=True)
    except Exception as e:
        current_app.logger.exception(f"LDAP bind technique failed: {e}")
        return None

    # 2) search user
    try:
        if not conn.search(search_base=base_dn, search_filter=user_filt, search_scope=SUBTREE, attributes=['cn','mail','uid','memberOf']):
            conn.unbind()
            return None
        if not conn.entries:
            conn.unbind()
            return None
        entry = conn.entries[0]
        user_dn = entry.entry_dn
        uid  = str(entry.uid) if 'uid' in entry else username
        cn   = str(entry.cn[0]) if 'cn' in entry and entry.cn else uid
        mail = str(entry.mail[0]) if 'mail' in entry and entry.mail else f"{uid}@example.org"
        ldap_groups = [str(g) for g in entry.memberOf] if 'memberOf' in entry else []

    except Exception as e:
        current_app.logger.exception(f"LDAP search failed: {e}")
        conn.unbind()
        return None

    # 3) verify group 
    if require_group:
        try:
            #ok = conn.search(search_base=require_group, search_filter=f"(member={user_dn})", attributes=['member'])
            ok = conn.search(
                search_base=require_group,
                search_filter=f"(memberUid={uid})", 
                search_scope=0, # BASE scope (0)
                attributes=['memberUid']
            )
            if not ok or not conn.entries:
                current_app.logger.warning(f"LDAP user {uid} not in required group {require_group}")
                conn.unbind(); return None
        except Exception as e:
            current_app.logger.exception(f"LDAP group check failed: {e}")
            conn.unbind(); return None

    # 4) bind as user
    try:
        if tls:
            uconn = Connection(server, user=user_dn, password=password, auto_bind=True, authentication=SIMPLE, read_only=True, tls=tls)
        else:
            uconn = Connection(server, user=user_dn, password=password, auto_bind=True, authentication=SIMPLE, read_only=True)
        uconn.unbind()
        conn.unbind()
        return User(uid=uid, cn=cn, mail=mail, groups=ldap_groups, is_admin=False, source="ldap")
    except Exception as e:
        current_app.logger.warning(f"LDAP bad credentials for {username}: {e}")
        conn.unbind()
        return None

# --- Fallback admin local ---
def local_admin_auth(username, password):
    if not bool(current_app.config.get('ENABLE_LOCAL_FALLBACK', True)):
        return None
    admin_user = current_app.config.get('LOCAL_ADMIN_USERNAME', 'admin')
    admin_hash = current_app.config.get('LOCAL_ADMIN_PASSWORD_HASH', '')
    if username != admin_user or not admin_hash:
        return None
    if check_password_hash(admin_hash, password):
        return User(uid=admin_user, cn='Local Admin', mail='admin@local', is_admin=True, source="local")
    return None

# --- Routes ---
@auth_bp.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')

        if not username or not password:
            flash("Identifiants manquants.", "error")
            return render_template('auth/login.html')

        if _too_many_attempts(username):
            flash("Trop de tentatives. Réessayez dans quelques minutes.", "error")
            return render_template('auth/login.html')

        # 1) LDAP first
        user = ldap_authenticate(username, password)
        # 2) fallback admin local
        if not user:
            user = local_admin_auth(username, password)

        if user:
            _reset_attempts(username)
            login_user(user)
            session['username'] = user.id
            session['fullname'] = user.cn
            session['email'] = user.mail
            session['auth_source'] = user.source
            #session['group'] = ", ".join(user.groups)
            return redirect(url_for('slurm.dashboard'))
        else:
            _register_failed_attempt(username)
            flash("Authentification failed.", "error")
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))