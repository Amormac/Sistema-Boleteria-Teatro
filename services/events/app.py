"""
Events & Seating Service — Puerto 7001
Maneja salas (venues), eventos y mapas de asientos.
Base de datos: PostgreSQL (venues, events) + MongoDB (seat_maps)
"""

import os
import datetime
import threading
import time
import psycopg2
import psycopg2.extras
import jwt
from flask import Flask, request, jsonify
from functools import wraps
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

app = Flask(__name__)

SECRET_KEY = os.environ.get('JWT_SECRET', 'super-secret-key-change-me')

# ── Conexión PostgreSQL ────────────────────────────────────────
def get_pg():
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        database=os.environ.get('POSTGRES_DB', 'teatro'),
        user=os.environ.get('POSTGRES_USER', 'teatro'),
        password=os.environ.get('POSTGRES_PASS', 'teatro123')
    )

# ── Conexión MongoDB ───────────────────────────────────────────
mongo_client = MongoClient(os.environ.get('MONGO_URI', 'mongodb://localhost:27017'))
mongo_db = mongo_client[os.environ.get('MONGO_DB', 'teatro')]
seat_maps = mongo_db['seat_maps']


# ── Decoradores de autenticación ──────────────────────────────
def _decode_token():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return None
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        data = _decode_token()
        if not data:
            return jsonify({'error': 'Token requerido o inválido'}), 401
        request.user_id = data['user_id']
        request.user_role = data['role']
        request.user_email = data.get('email', '')
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        data = _decode_token()
        if not data:
            return jsonify({'error': 'Token requerido o inválido'}), 401
        if data['role'] != 'ADMIN':
            return jsonify({'error': 'Acceso denegado: se requiere rol ADMIN'}), 403
        request.user_id = data['user_id']
        request.user_role = data['role']
        request.user_email = data.get('email', '')
        return f(*args, **kwargs)
    return decorated


def audit(user_id, action, detail=''):
    try:
        conn = get_pg()
        with conn.cursor() as cur:
            ip = request.remote_addr or ''
            cur.execute(
                "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (%s,%s,%s,%s)",
                (user_id, action, detail, ip)
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Helper: serializar filas PG ────────────────────────────────
def _serialize_row(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.isoformat()
        elif hasattr(v, 'is_finite'):  # Decimal
            d[k] = float(v)
    return d


# ═══════════════════════════════════════════════════════════════
#  VENUES (SALAS)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/venues', methods=['GET'])
@token_required
def list_venues():
    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM venues ORDER BY created_at DESC")
            venues = [_serialize_row(v) for v in cur.fetchall()]

            # Check for active events
            for venue in venues:
                cur.execute("SELECT 1 FROM events WHERE venue_id = %s AND status != 'CLOSED' LIMIT 1", (venue['id'],))
                venue['has_active_events'] = bool(cur.fetchone())
        return jsonify(venues)
    finally:
        conn.close()


@app.route('/api/venues', methods=['POST'])
@admin_required
def create_venue():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    rows_count = int(data.get('rows_count', 0))
    cols_count = int(data.get('cols_count', 0))
    image_main = data.get('image_main', '').strip()
    image_gallery = data.get('image_gallery', [])  # Expecting list of strings

    if not name or rows_count <= 0 or cols_count <= 0:
        return jsonify({'error': 'Nombre, filas y columnas son requeridos (filas > 0, columnas > 0)'}), 400
    if rows_count > 26:
        return jsonify({'error': 'Máximo 26 filas (A-Z)'}), 400

    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO venues (name, rows_count, cols_count, image_main, image_gallery) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (name, rows_count, cols_count, image_main, psycopg2.extras.Json(image_gallery))
            )
            venue = _serialize_row(cur.fetchone())
        conn.commit()
        audit(request.user_id, 'CREATE_VENUE', f'{name} ({rows_count}x{cols_count})')
        return jsonify(venue), 201
    finally:
        conn.close()


@app.route('/api/venues/<int:venue_id>', methods=['PUT'])
@admin_required
def update_venue(venue_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    image_main = data.get('image_main', '').strip()
    image_gallery = data.get('image_gallery', [])

    rows_count = int(data.get('rows_count', 0))
    cols_count = int(data.get('cols_count', 0))

    if not name:
        return jsonify({'error': 'Nombre es requerido'}), 400

    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check if venue exists
            cur.execute("SELECT * FROM venues WHERE id = %s", (venue_id,))
            current_venue = cur.fetchone()
            if not current_venue:
                return jsonify({'error': 'Sala no encontrada'}), 404

            # Dimension update validation
            new_rows = rows_count if rows_count > 0 else current_venue['rows_count']
            new_cols = cols_count if cols_count > 0 else current_venue['cols_count']

            if new_rows != current_venue['rows_count'] or new_cols != current_venue['cols_count']:
                # Check for active/draft events
                cur.execute("SELECT id FROM events WHERE venue_id = %s AND status != 'CLOSED'", (venue_id,))
                if cur.fetchone():
                    return jsonify({'error': 'No se pueden modificar las dimensiones porque hay eventos activos o en borrador en esta sala.'}), 400
            
            cur.execute(
                "UPDATE venues SET name=%s, rows_count=%s, cols_count=%s, image_main=%s, image_gallery=%s WHERE id=%s RETURNING *",
                (name, new_rows, new_cols, image_main, psycopg2.extras.Json(image_gallery), venue_id)
            )
            venue = _serialize_row(cur.fetchone())
        conn.commit()
        audit(request.user_id, 'UPDATE_VENUE', f'{venue["name"]} (ID: {venue_id})')
        return jsonify(venue)
    finally:
        conn.close()


@app.route('/api/venues/<int:venue_id>', methods=['DELETE'])
@admin_required
def delete_venue(venue_id):
    conn = get_pg()
    try:
        with conn.cursor() as cur:
            # Check constraints: Cannot delete if active events exist
            cur.execute("SELECT COUNT(*) FROM events WHERE venue_id = %s AND status != 'CLOSED'", (venue_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({'error': 'No se puede eliminar: la sala tiene eventos activos o borradores.'}), 409

            cur.execute("DELETE FROM venues WHERE id = %s RETURNING id", (venue_id,))
            if not cur.fetchone():
                return jsonify({'error': 'Sala no encontrada'}), 404
        conn.commit()
        audit(request.user_id, 'DELETE_VENUE', f'ID: {venue_id}')
        return jsonify({'message': 'Sala eliminada correctamente'})
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  EVENTS (EVENTOS)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/events', methods=['GET'])
def list_events():
    status = request.args.get('status', None)
    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if status:
                cur.execute("""
                    SELECT e.*, v.name AS venue_name, v.rows_count, v.cols_count
                    FROM events e JOIN venues v ON e.venue_id = v.id
                    WHERE e.status = %s ORDER BY e.start_time
                """, (status,))
            else:
                cur.execute("""
                    SELECT e.*, v.name AS venue_name, v.rows_count, v.cols_count
                    FROM events e JOIN venues v ON e.venue_id = v.id
                    ORDER BY e.start_time
                """)
            events = [_serialize_row(e) for e in cur.fetchall()]
        return jsonify(events)
    finally:
        conn.close()


@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT e.*, v.name AS venue_name, v.rows_count, v.cols_count
                FROM events e JOIN venues v ON e.venue_id = v.id
                WHERE e.id = %s
            """, (event_id,))
            event = cur.fetchone()
        if not event:
            return jsonify({'error': 'Evento no encontrado'}), 404
        return jsonify(_serialize_row(event))
    finally:
        conn.close()


@app.route('/api/events', methods=['POST'])
@admin_required
def create_event():
    data = request.get_json() or {}
    venue_id = data.get('venue_id')
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    price = float(data.get('price', 0))
    max_per_user = int(data.get('max_per_user', 4))

    if not venue_id or not title or not start_time or not end_time:
        return jsonify({'error': 'venue_id, title, start_time y end_time son requeridos'}), 400

    # Validar fechas
    try:
        start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de fecha inválido (ISO 8601 requerida)'}), 400

    if end_dt <= start_dt:
        return jsonify({'error': 'La hora de fin debe ser posterior a la de inicio'}), 400
    
    if (end_dt - start_dt).total_seconds() < 900: # 15 min
        return jsonify({'error': 'El evento debe durar al menos 15 minutos'}), 400

    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Verificar sala
            cur.execute("SELECT * FROM venues WHERE id = %s", (venue_id,))
            venue = cur.fetchone()
            if not venue:
                return jsonify({'error': 'Sala no encontrada'}), 404

            # Verificar traslape
            # (StartA <= EndB) and (EndA >= StartB)
            cur.execute("""
                SELECT id FROM events 
                WHERE venue_id = %s 
                AND status != 'CLOSED'
                AND NOT (end_time <= %s OR start_time >= %s)
            """, (venue_id, start_time, end_time))
            
            if cur.fetchone():
                return jsonify({'error': 'Ya existe un evento en ese horario para esta sala'}), 409

            cur.execute("""
                INSERT INTO events (venue_id, title, description, start_time, end_time, price, max_per_user, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'DRAFT') RETURNING *
            """, (venue_id, title, description, start_time, end_time, price, max_per_user))
            event = _serialize_row(cur.fetchone())
        conn.commit()

        # Crear mapa de asientos en MongoDB
        seats = {}
        for r in range(venue['rows_count']):
            row_letter = chr(65 + r)
            for c in range(1, venue['cols_count'] + 1):
                seat_id = f"{row_letter}{c}"
                seats[seat_id] = {
                    'status': 'FREE',
                    'zone': 'GENERAL',
                    'held_by': None,
                    'hold_until': None
                }

        seat_maps.insert_one({
            'event_id': event['id'],
            'venue_id': venue['id'],
            'venue_name': venue['name'],
            'rows': venue['rows_count'],
            'cols': venue['cols_count'],
            'seats': seats
        })

        audit(request.user_id, 'CREATE_EVENT', f'{title} (sala {venue["name"]})')
        return jsonify(event), 201
    finally:
        conn.close()


@app.route('/api/events/<int:event_id>/status', methods=['PUT'])
@admin_required
def update_event_status(event_id):
    data = request.get_json() or {}
    new_status = data.get('status', '').upper()

    if new_status not in ('DRAFT', 'ACTIVE', 'CLOSED'):
        return jsonify({'error': 'Estado inválido (DRAFT, ACTIVE, CLOSED)'}), 400

    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE events SET status = %s WHERE id = %s RETURNING *",
                (new_status, event_id)
            )
            event = cur.fetchone()
            if not event:
                return jsonify({'error': 'Evento no encontrado'}), 404
        conn.commit()
        audit(request.user_id, 'UPDATE_EVENT_STATUS', f'Evento {event_id} → {new_status}')
        return jsonify(_serialize_row(event))
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  SEAT MAP (MAPA DE ASIENTOS — MongoDB)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/events/<int:event_id>/seats', methods=['GET'])
def get_seats(event_id):
    """Devuelve el mapa de asientos con holds expirados limpiados."""
    doc = seat_maps.find_one({'event_id': event_id}, {'_id': 0})
    if not doc:
        return jsonify({'error': 'Mapa de asientos no encontrado'}), 404

    now = datetime.datetime.utcnow()
    cleaned = 0
    for seat_id, seat in doc.get('seats', {}).items():
        if seat['status'] == 'HELD' and seat.get('hold_until'):
            if seat['hold_until'] < now:
                seat['status'] = 'FREE'
                seat['held_by'] = None
                seat['hold_until'] = None
                cleaned += 1

    # Actualizar en Mongo los asientos expirados (batch)
    if cleaned > 0:
        _release_expired(event_id)

    # Serializar hold_until a string
    for seat_id, seat in doc.get('seats', {}).items():
        if seat.get('hold_until') and isinstance(seat['hold_until'], datetime.datetime):
            seat['hold_until'] = seat['hold_until'].isoformat()

    return jsonify(doc)


@app.route('/api/events/<int:event_id>/hold', methods=['POST'])
@token_required
def hold_seats(event_id):
    """
    Reserva temporal (HOLD) de asientos por 10 minutos.
    Operación atómica en MongoDB para concurrencia.
    Body: { "seats": ["A1", "A2"] }
    """
    data = request.get_json() or {}
    requested_seats = data.get('seats', [])

    if not requested_seats:
        return jsonify({'error': 'Debe seleccionar al menos un asiento'}), 400

    # Verificar evento activo
    conn = get_pg()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            event = cur.fetchone()
    finally:
        conn.close()

    if not event:
        return jsonify({'error': 'Evento no encontrado'}), 404
    if event['status'] != 'ACTIVE':
        return jsonify({'error': 'El evento no está activo'}), 400

    # Verificar límite de boletos por usuario
    max_per_user = event['max_per_user']
    doc = seat_maps.find_one({'event_id': event_id})
    if not doc:
        return jsonify({'error': 'Mapa de asientos no encontrado'}), 404

    # Contar asientos ya reservados/vendidos por este usuario
    user_seat_count = 0
    for sid, s in doc.get('seats', {}).items():
        if s.get('held_by') == request.user_id and s['status'] in ('HELD', 'SOLD'):
            if s['status'] == 'HELD' and s.get('hold_until'):
                if s['hold_until'] >= datetime.datetime.utcnow():
                    user_seat_count += 1
            elif s['status'] == 'SOLD':
                user_seat_count += 1

    if user_seat_count + len(requested_seats) > max_per_user:
        return jsonify({
            'error': f'Excedes el límite de {max_per_user} boletos por usuario. Ya tienes {user_seat_count}.'
        }), 400

    # Intentar HOLD atómico para cada asiento
    now = datetime.datetime.utcnow()
    hold_until = now + datetime.timedelta(minutes=10)
    held = []
    failed = []

    for seat_id in requested_seats:
        result = seat_maps.find_one_and_update(
            {
                'event_id': event_id,
                '$or': [
                    {f'seats.{seat_id}.status': 'FREE'},
                    {
                        f'seats.{seat_id}.status': 'HELD',
                        f'seats.{seat_id}.hold_until': {'$lt': now}
                    }
                ]
            },
            {
                '$set': {
                    f'seats.{seat_id}.status': 'HELD',
                    f'seats.{seat_id}.held_by': request.user_id,
                    f'seats.{seat_id}.hold_until': hold_until
                }
            }
        )
        if result:
            held.append(seat_id)
        else:
            failed.append(seat_id)

    # Si alguno falló, liberar los que sí se reservaron
    if failed and held:
        for seat_id in held:
            seat_maps.update_one(
                {'event_id': event_id},
                {'$set': {
                    f'seats.{seat_id}.status': 'FREE',
                    f'seats.{seat_id}.held_by': None,
                    f'seats.{seat_id}.hold_until': None
                }}
            )
        return jsonify({
            'error': f'No se pudieron reservar todos los asientos. Ocupados: {", ".join(failed)}'
        }), 409

    if failed:
        return jsonify({
            'error': f'Asientos no disponibles: {", ".join(failed)}'
        }), 409

    audit(request.user_id, 'HOLD_SEATS', f'Evento {event_id}: {", ".join(held)}')
    return jsonify({
        'message': 'Asientos reservados temporalmente (10 min)',
        'seats': held,
        'hold_until': hold_until.isoformat(),
        'event_id': event_id
    })


@app.route('/api/events/<int:event_id>/release', methods=['POST'])
@token_required
def release_seats(event_id):
    """Libera asientos en HOLD del usuario actual."""
    data = request.get_json() or {}
    seats_to_release = data.get('seats', [])

    if not seats_to_release:
        return jsonify({'error': 'Debe indicar asientos a liberar'}), 400

    released = []
    for seat_id in seats_to_release:
        result = seat_maps.find_one_and_update(
            {
                'event_id': event_id,
                f'seats.{seat_id}.status': 'HELD',
                f'seats.{seat_id}.held_by': request.user_id
            },
            {
                '$set': {
                    f'seats.{seat_id}.status': 'FREE',
                    f'seats.{seat_id}.held_by': None,
                    f'seats.{seat_id}.hold_until': None
                }
            }
        )
        if result:
            released.append(seat_id)

    return jsonify({'released': released})


@app.route('/api/events/<int:event_id>/confirm-seats', methods=['POST'])
@token_required
def confirm_seats(event_id):
    """
    Marca asientos como SOLD (llamado desde Orders Service tras confirmar compra).
    Body: { "seats": ["A1","A2"], "user_id": 5 }
    """
    data = request.get_json() or {}
    seats_to_confirm = data.get('seats', [])
    user_id = data.get('user_id', request.user_id)

    confirmed = []
    for seat_id in seats_to_confirm:
        result = seat_maps.find_one_and_update(
            {
                'event_id': event_id,
                f'seats.{seat_id}.status': 'HELD',
                f'seats.{seat_id}.held_by': user_id
            },
            {
                '$set': {
                    f'seats.{seat_id}.status': 'SOLD',
                    f'seats.{seat_id}.hold_until': None
                }
            }
        )
        if result:
            confirmed.append(seat_id)

    return jsonify({'confirmed': confirmed})


@app.route('/api/events/<int:event_id>/stats', methods=['GET'])
@admin_required
def event_stats(event_id):
    """Estadísticas del evento: asientos free/held/sold."""
    doc = seat_maps.find_one({'event_id': event_id}, {'_id': 0})
    if not doc:
        return jsonify({'error': 'Mapa no encontrado'}), 404

    now = datetime.datetime.utcnow()
    stats = {'free': 0, 'held': 0, 'sold': 0, 'total': 0}
    for seat_id, seat in doc.get('seats', {}).items():
        stats['total'] += 1
        status = seat['status']
        if status == 'HELD' and seat.get('hold_until') and seat['hold_until'] < now:
            stats['free'] += 1
        elif status == 'FREE':
            stats['free'] += 1
        elif status == 'HELD':
            stats['held'] += 1
        elif status == 'SOLD':
            stats['sold'] += 1

    return jsonify(stats)


# ═══════════════════════════════════════════════════════════════
#  Limpieza automática de holds expirados (background thread)
# ═══════════════════════════════════════════════════════════════

def _release_expired(event_id=None):
    """Libera todos los holds expirados de un evento (o todos)."""
    now = datetime.datetime.utcnow()
    query = {} if event_id is None else {'event_id': event_id}

    for doc in seat_maps.find(query):
        updates = {}
        for seat_id, seat in doc.get('seats', {}).items():
            if seat['status'] == 'HELD' and seat.get('hold_until') and seat['hold_until'] < now:
                updates[f'seats.{seat_id}.status'] = 'FREE'
                updates[f'seats.{seat_id}.held_by'] = None
                updates[f'seats.{seat_id}.hold_until'] = None
        if updates:
            seat_maps.update_one({'_id': doc['_id']}, {'$set': updates})


def hold_cleanup_worker():
    """Hilo en segundo plano que limpia holds expirados cada 30 segundos."""
    while True:
        try:
            _release_expired()
        except Exception as e:
            print(f"[HOLD CLEANUP] Error: {e}")
        time.sleep(30)


# ── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    # Iniciar hilo de limpieza
    cleanup_thread = threading.Thread(target=hold_cleanup_worker, daemon=True)
    cleanup_thread.start()
    print("🧹 Hilo de limpieza de holds iniciado (cada 30s)")

    port = int(os.environ.get('SEATING_PORT', 7001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f"🎭 Events & Seating Service iniciando en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
