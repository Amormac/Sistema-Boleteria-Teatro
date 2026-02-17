"""
Web Gateway / Frontend — Puerto 8080
Sirve la interfaz web (HTML/CSS/JS) y hace proxy a los microservicios.
"""

import os
import jwt as pyjwt
import requests as http_requests
from werkzeug.utils import secure_filename
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, send_from_directory)
from functools import wraps
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

app = Flask(__name__)
# app.secret_key defaults to 'dev_secret_key' if env var not set
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Configure Uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'venues')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

SECRET_KEY = os.environ.get('JWT_SECRET', 'super-secret-key-change-me')
AUTH_URL = os.environ.get('AUTH_SERVICE_URL', 'http://localhost:7000')
EVENTS_URL = os.environ.get('EVENTS_SERVICE_URL', 'http://localhost:7001')
ORDERS_URL = os.environ.get('ORDERS_SERVICE_URL', 'http://localhost:7002')
TIMEOUT = 8


# ── Helpers ────────────────────────────────────────────────────

def get_current_user():
    """Decodifica el JWT almacenado en sesión."""
    token = session.get('token')
    if not token:
        return None
    try:
        data = pyjwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return data
    except Exception:
        session.pop('token', None)
        return None


def auth_headers():
    token = session.get('token', '')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login_page'))
        request.user = user
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Debes iniciar sesión.', 'warning')
            return redirect(url_for('login_page'))
        if user.get('role') != 'ADMIN':
            flash('No tienes permisos de administrador.', 'danger')
            return redirect(url_for('index'))
        request.user = user
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════════
#  PÁGINAS PÚBLICAS
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    user = get_current_user()
    events = []
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events?status=ACTIVE', timeout=TIMEOUT)
        if resp.status_code == 200:
            events = resp.json()
    except Exception:
        flash('No se pudo conectar con el servicio de eventos.', 'danger')
    return render_template('index.html', user=user, events=events)


@app.route('/login', methods=['GET'])
def login_page():
    user = get_current_user()
    if user:
        return redirect(url_for('index'))
    return render_template('login.html', user=None)


@app.route('/login', methods=['POST'])
def login_action():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    try:
        resp = http_requests.post(f'{AUTH_URL}/api/auth/login',
                                  json={'email': email, 'password': password},
                                  timeout=TIMEOUT)
        data = resp.json()
        if resp.status_code == 200:
            session['token'] = data['token']
            flash(f'¡Bienvenido, {data["user"]["name"]}!', 'success')
            if data['user']['role'] == 'ADMIN':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        else:
            flash(data.get('error', 'Error de autenticación'), 'danger')
    except Exception:
        flash('No se pudo conectar con el servicio de autenticación.', 'danger')
    return redirect(url_for('login_page'))


@app.route('/register', methods=['GET'])
def register_page():
    user = get_current_user()
    if user:
        return redirect(url_for('index'))
    return render_template('register.html', user=None)


@app.route('/register', methods=['POST'])
def register_action():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    password2 = request.form.get('password2', '')

    if password != password2:
        flash('Las contraseñas no coinciden.', 'danger')
        return redirect(url_for('register_page'))

    try:
        resp = http_requests.post(f'{AUTH_URL}/api/auth/register',
                                  json={'name': name, 'email': email, 'password': password},
                                  timeout=TIMEOUT)
        data = resp.json()
        if resp.status_code == 201:
            session['token'] = data['token']
            flash('¡Cuenta creada con éxito! Bienvenido.', 'success')
            return redirect(url_for('index'))
        else:
            flash(data.get('error', 'Error al registrarse'), 'danger')
    except Exception:
        flash('No se pudo conectar con el servicio de autenticación.', 'danger')
    return redirect(url_for('register_page'))


@app.route('/logout')
def logout():
    session.pop('token', None)
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('index'))


# ═══════════════════════════════════════════════════════════════
#  DETALLE DE EVENTO + MAPA DE ASIENTOS
# ═══════════════════════════════════════════════════════════════

@app.route('/event/<int:event_id>')
@login_required
def event_detail(event_id):
    user = get_current_user()
    event = None
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events/{event_id}', timeout=TIMEOUT)
        if resp.status_code == 200:
            event = resp.json()
    except Exception:
        flash('Error al obtener el evento.', 'danger')
    if not event:
        flash('Evento no encontrado.', 'warning')
        return redirect(url_for('index'))
    return render_template('event_detail.html', user=user, event=event)


# ── API JSON para el frontend JS ──

@app.route('/api/seats/<int:event_id>')
@login_required
def api_seats(event_id):
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events/{event_id}/seats', timeout=TIMEOUT)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hold', methods=['POST'])
@login_required
def api_hold():
    data = request.get_json() or {}
    event_id = data.get('event_id')
    seats = data.get('seats', [])
    try:
        resp = http_requests.post(
            f'{EVENTS_URL}/api/events/{event_id}/hold',
            json={'seats': seats},
            headers=auth_headers(),
            timeout=TIMEOUT
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/release', methods=['POST'])
@login_required
def api_release():
    data = request.get_json() or {}
    event_id = data.get('event_id')
    seats = data.get('seats', [])
    try:
        resp = http_requests.post(
            f'{EVENTS_URL}/api/events/{event_id}/release',
            json={'seats': seats},
            headers=auth_headers(),
            timeout=TIMEOUT
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/purchase', methods=['POST'])
@login_required
def api_purchase():
    """Crea orden y confirma de inmediato (pago simulado)."""
    data = request.get_json() or {}
    event_id = data.get('event_id')
    seats = data.get('seats', [])

    # 1) Crear orden
    try:
        resp = http_requests.post(
            f'{ORDERS_URL}/api/orders',
            json={'event_id': event_id, 'seats': seats},
            headers=auth_headers(),
            timeout=TIMEOUT
        )
        if resp.status_code != 201:
            return jsonify(resp.json()), resp.status_code
        order = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # 2) Confirmar orden (pago simulado)
    try:
        resp2 = http_requests.post(
            f'{ORDERS_URL}/api/orders/{order["id"]}/confirm',
            headers=auth_headers(),
            timeout=TIMEOUT
        )
        return jsonify(resp2.json()), resp2.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
#  MIS TICKETS
# ═══════════════════════════════════════════════════════════════

@app.route('/my-tickets')
@login_required
def my_tickets():
    user = get_current_user()
    orders = []
    try:
        resp = http_requests.get(f'{ORDERS_URL}/api/orders/my',
                                 headers=auth_headers(), timeout=TIMEOUT)
        if resp.status_code == 200:
            orders = resp.json()
    except Exception:
        flash('Error al obtener tus tickets.', 'danger')
    return render_template('my_tickets.html', user=user, orders=orders)


# ═══════════════════════════════════════════════════════════════
#  PANEL DE ADMINISTRACIÓN
# ═══════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin_dashboard():
    user = get_current_user()
    events = []
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events', timeout=TIMEOUT)
        if resp.status_code == 200:
            events = resp.json()
    except Exception:
        pass
    return render_template('admin/dashboard.html', user=user, events=events)


@app.route('/admin/venues')
@admin_required
def admin_venues():
    user = get_current_user()
    venues = []
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/venues',
                                 headers=auth_headers(), timeout=TIMEOUT)
        if resp.status_code == 200:
            venues = resp.json()
    except Exception:
        flash('Error al obtener las salas.', 'danger')
    return render_template('admin/venues.html', user=user, venues=venues)


@app.route('/admin/venues/create', methods=['POST'])
@admin_required
def admin_create_venue():
    try:
        # 1. Handle File Uploads
        image_main_url = ""
        if 'image_main' in request.files:
            file = request.files['image_main']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Unique filename to avoid collisions could be added here
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                image_main_url = url_for('static', filename=f'uploads/venues/{filename}', _external=True)

        image_gallery_urls = []
        if 'image_gallery' in request.files:
            files = request.files.getlist('image_gallery')
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    url = url_for('static', filename=f'uploads/venues/{filename}', _external=True)
                    image_gallery_urls.append(url)

        # 2. Prepare Payload
        payload = {
            'name': request.form.get('name'),
            'rows_count': int(request.form.get('rows_count')),
            'cols_count': int(request.form.get('cols_count')),
            'image_main': image_main_url,
            'image_gallery': image_gallery_urls
        }

        # 3. Send to Events Service
        admin_token = session.get('token')
        resp = http_requests.post(
            f"{EVENTS_URL}/api/venues",
            json=payload,
            headers={'Authorization': f'Bearer {admin_token}'},
            timeout=TIMEOUT
        )
        if resp.status_code == 201:
            flash(f'Sala "{payload["name"]}" creada con éxito.', 'success')
        else:
            flash(resp.json().get('error', 'Error'), 'danger')
    except Exception:
        flash('Error de conexión.', 'danger')
    return redirect(url_for('admin_venues'))


@app.route('/admin/venues/<int:venue_id>/edit', methods=['POST'])
@admin_required
def admin_update_venue(venue_id):
    try:
        # 1. Image Main
        image_main_url = request.form.get('current_image_main', '')
        if 'image_main' in request.files:
            file = request.files['image_main']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                image_main_url = url_for('static', filename=f'uploads/venues/{filename}', _external=True)

        # 2. Image Gallery
        # If files are uploaded, they REPLACE the current gallery.
        # If no files uploaded, keep current.
        image_gallery_urls = []
        has_new_gallery = False
        if 'image_gallery' in request.files:
            files = request.files.getlist('image_gallery')
            # Check if at least one file is valid
            if any(f.filename for f in files):
                has_new_gallery = True
                for file in files:
                    if file and file.filename != '':
                        filename = secure_filename(file.filename)
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        url = url_for('static', filename=f'uploads/venues/{filename}', _external=True)
                        image_gallery_urls.append(url)
        
        if not has_new_gallery:
             # Fallback to current
             raw_current = request.form.get('current_image_gallery', '')
             image_gallery_urls = [u.strip() for u in raw_current.split(',') if u.strip()]

        payload = {
            'name': request.form.get('name'),
            'rows_count': int(request.form.get('rows_count')),
            'cols_count': int(request.form.get('cols_count')),
            'image_main': image_main_url,
            'image_gallery': image_gallery_urls
        }

        admin_token = session.get('token')
        resp = http_requests.put(
            f"{EVENTS_URL}/api/venues/{venue_id}",
            json=payload,
            headers={'Authorization': f'Bearer {admin_token}'},
            timeout=TIMEOUT
        )
        if resp.status_code == 200:
            flash('Sala actualizada correctamente.', 'success')
        else:
            flash(resp.json().get('error', 'Error al actualizar'), 'danger')

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('admin_venues'))


@app.route('/admin/venues/<int:venue_id>/delete', methods=['POST'])
@admin_required
def admin_delete_venue(venue_id):
    try:
        resp = http_requests.delete(
            f'{EVENTS_URL}/api/venues/{venue_id}',
            headers=auth_headers(), timeout=TIMEOUT
        )
        if resp.status_code == 200:
            flash('Sala eliminada correctamente.', 'success')
        else:
            flash(resp.json().get('error', 'Error al eliminar.'), 'danger')
    except Exception:
        flash('Error de conexión.', 'danger')
    return redirect(url_for('admin_venues'))


@app.route('/admin/events')
@admin_required
def admin_events():
    user = get_current_user()
    events = []
    venues = []
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events', timeout=TIMEOUT)
        if resp.status_code == 200:
            events = resp.json()
        resp2 = http_requests.get(f'{EVENTS_URL}/api/venues',
                                  headers=auth_headers(), timeout=TIMEOUT)
        if resp2.status_code == 200:
            venues = resp2.json()
    except Exception:
        flash('Error de conexión.', 'danger')
    return render_template('admin/events.html', user=user, events=events, venues=venues)


@app.route('/admin/events', methods=['POST'])
@admin_required
def admin_create_event():
    payload = {
        'venue_id': request.form.get('venue_id', default=0, type=int),
        'title': request.form.get('title', '').strip(),
        'description': request.form.get('description', '').strip(),
        'start_time': request.form.get('start_time', ''),
        'end_time': request.form.get('end_time', ''),
        'price': request.form.get('price', default=0.0, type=float),
        'max_per_user': request.form.get('max_per_user', default=4, type=int)
    }
    try:
        resp = http_requests.post(f'{EVENTS_URL}/api/events',
                                  json=payload, headers=auth_headers(), timeout=TIMEOUT)
        if resp.status_code == 201:
            flash(f'Evento "{payload["title"]}" creado.', 'success')
        else:
            flash(resp.json().get('error', 'Error'), 'danger')
    except Exception:
        flash('Error de conexión.', 'danger')
    return redirect(url_for('admin_events'))


@app.route('/admin/events/<int:event_id>/status', methods=['POST'])
@admin_required
def admin_event_status(event_id):
    new_status = request.form.get('status', 'ACTIVE')
    try:
        resp = http_requests.put(
            f'{EVENTS_URL}/api/events/{event_id}/status',
            json={'status': new_status},
            headers=auth_headers(), timeout=TIMEOUT
        )
        if resp.status_code == 200:
            flash(f'Estado del evento actualizado a {new_status}.', 'success')
        else:
            flash(resp.json().get('error', 'Error'), 'danger')
    except Exception:
        flash('Error de conexión.', 'danger')
    return redirect(url_for('admin_events'))


@app.route('/admin/events/<int:event_id>/sales')
@admin_required
def admin_event_sales(event_id):
    user = get_current_user()
    event = None
    orders = []
    stats = {}
    try:
        resp = http_requests.get(f'{EVENTS_URL}/api/events/{event_id}', timeout=TIMEOUT)
        if resp.status_code == 200:
            event = resp.json()
        resp2 = http_requests.get(
            f'{ORDERS_URL}/api/orders/event/{event_id}',
            headers=auth_headers(), timeout=TIMEOUT
        )
        if resp2.status_code == 200:
            orders = resp2.json()
        resp3 = http_requests.get(
            f'{EVENTS_URL}/api/events/{event_id}/stats',
            headers=auth_headers(), timeout=TIMEOUT
        )
        if resp3.status_code == 200:
            stats = resp3.json()
    except Exception:
        flash('Error obteniendo datos de ventas.', 'danger')

    return render_template('admin/event_sales.html',
                           user=user, event=event, orders=orders, stats=stats)


# ── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('WEB_PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f"🌐 Web Gateway iniciando en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
