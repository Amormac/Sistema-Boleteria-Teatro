"""
Auth Service — Puerto 7000
Maneja registro, login, verificación de token JWT.
Base de datos: PostgreSQL (tabla users, audit_log)
"""

import os
import datetime
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
from flask import Flask, request, jsonify
from functools import wraps
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

app = Flask(__name__)

SECRET_KEY = os.environ.get('JWT_SECRET', 'super-secret-key-change-me')


# ── Conexión a PostgreSQL ──────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        database=os.environ.get('POSTGRES_DB', 'teatro'),
        user=os.environ.get('POSTGRES_USER', 'teatro'),
        password=os.environ.get('POSTGRES_PASS', 'teatro123')
    )


# ── Decoradores de autenticación ──────────────────────────────
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_role = data['role']
            request.user_email = data['email']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            if data['role'] != 'ADMIN':
                return jsonify({'error': 'Acceso denegado: se requiere rol ADMIN'}), 403
            request.user_id = data['user_id']
            request.user_role = data['role']
            request.user_email = data['email']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Utilidades ─────────────────────────────────────────────────
def make_token(user):
    """Genera un JWT con expiración de 24 h."""
    return jwt.encode({
        'user_id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'role': user['role'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, SECRET_KEY, algorithm='HS256')


def audit(conn, user_id, action, detail=''):
    with conn.cursor() as cur:
        ip = request.remote_addr or ''
        cur.execute(
            "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (%s,%s,%s,%s)",
            (user_id, action, detail, ip)
        )
    conn.commit()


# ── Endpoints ──────────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip()

    if not email or not password:
        return jsonify({'error': 'Email y contraseña son requeridos'}), 400
    if len(password) < 6:
        return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, name, role) "
                "VALUES (%s, %s, %s, 'USER') RETURNING id, email, name, role",
                (email, password_hash, name)
            )
            user = cur.fetchone()
            conn.commit()

        audit(conn, user['id'], 'REGISTER', f'Registro: {email}')
        token = make_token(user)
        return jsonify({'token': token, 'user': dict(user)}), 201

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({'error': 'El email ya está registrado'}), 409
    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s AND enabled = true", (email,))
            user = cur.fetchone()

        if not user:
            return jsonify({'error': 'Credenciales inválidas'}), 401

        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({'error': 'Credenciales inválidas'}), 401

        audit(conn, user['id'], 'LOGIN', f'Inicio de sesión: {email}')
        token = make_token(user)
        return jsonify({
            'token': token,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'name': user['name'],
                'role': user['role']
            }
        })
    finally:
        conn.close()


@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, name, role, created_at FROM users WHERE id = %s",
                (request.user_id,)
            )
            user = cur.fetchone()
        if not user:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        user['created_at'] = user['created_at'].isoformat()
        return jsonify(user)
    finally:
        conn.close()


@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify():
    """Endpoint interno para que otros servicios verifiquen el token."""
    return jsonify({
        'user_id': request.user_id,
        'email': request.user_email,
        'role': request.user_role
    })


# ── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('AUTH_PORT', 7000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f"🔐 Auth Service iniciando en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
