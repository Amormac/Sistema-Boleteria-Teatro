"""
Orders Service — Puerto 7002
Maneja órdenes de compra y generación de tickets.
Base de datos: PostgreSQL (orders, tickets)
Llama internamente al Events Service para confirmar asientos.
"""

import os
import uuid
import datetime
import psycopg2
import psycopg2.extras
import jwt
import requests as http_requests
from flask import Flask, request, jsonify
from functools import wraps
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

app = Flask(__name__)

SECRET_KEY = os.environ.get('JWT_SECRET', 'super-secret-key-change-me')
EVENTS_SERVICE_URL = os.environ.get('EVENTS_SERVICE_URL', 'http://localhost:7001')


# ── Conexión PostgreSQL ────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        database=os.environ.get('POSTGRES_DB', 'teatro'),
        user=os.environ.get('POSTGRES_USER', 'teatro'),
        password=os.environ.get('POSTGRES_PASS', 'teatro123')
    )


# ── Decoradores ────────────────────────────────────────────────
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
        request.token_raw = request.headers.get('Authorization', '').replace('Bearer ', '')
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        data = _decode_token()
        if not data:
            return jsonify({'error': 'Token requerido o inválido'}), 401
        if data['role'] != 'ADMIN':
            return jsonify({'error': 'Acceso denegado'}), 403
        request.user_id = data['user_id']
        request.user_role = data['role']
        request.user_email = data.get('email', '')
        request.token_raw = request.headers.get('Authorization', '').replace('Bearer ', '')
        return f(*args, **kwargs)
    return decorated


def audit(conn, user_id, action, detail=''):
    try:
        with conn.cursor() as cur:
            ip = request.remote_addr or ''
            cur.execute(
                "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (%s,%s,%s,%s)",
                (user_id, action, detail, ip)
            )
        conn.commit()
    except Exception:
        pass


def _serialize_row(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.isoformat()
        elif hasattr(v, 'is_finite'):
            d[k] = float(v)
    return d


def generate_ticket_code():
    return f"TCK-{uuid.uuid4().hex[:8].upper()}"


# ═══════════════════════════════════════════════════════════════
#  ORDERS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/orders', methods=['POST'])
@token_required
def create_order():
    """
    Crea una orden PENDING. Los asientos ya deben estar en HOLD.
    Body: { "event_id": 1, "seats": ["A1","A2"] }
    """
    data = request.get_json() or {}
    event_id = data.get('event_id')
    seats = data.get('seats', [])

    if not event_id or not seats:
        return jsonify({'error': 'event_id y seats son requeridos'}), 400

    # Obtener info del evento
    try:
        resp = http_requests.get(
            f'{EVENTS_SERVICE_URL}/api/events/{event_id}',
            headers={'Authorization': f'Bearer {request.token_raw}'},
            timeout=5
        )
        if resp.status_code != 200:
            return jsonify({'error': 'Evento no encontrado'}), 404
        event = resp.json()
    except Exception as e:
        return jsonify({'error': f'Error contactando Events Service: {str(e)}'}), 500

    price = float(event.get('price', 0))
    total = price * len(seats)

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Verificar límite de tickets acumulado
            cur.execute("""
                SELECT COALESCE(SUM(seat_count), 0) as total
                FROM orders 
                WHERE user_id = %s AND event_id = %s AND status IN ('PENDING', 'CONFIRMED')
            """, (request.user_id, event_id))
            match = cur.fetchone()
            current_total = match['total'] if match else 0
            
            max_allowed = int(event.get('max_per_user', 4))
            if current_total + len(seats) > max_allowed:
                 return jsonify({'error': f'Excedes el límite de {max_allowed} boletos por usuario. Ya tienes {current_total} boletos.'}), 400

            cur.execute("""
                INSERT INTO orders (user_id, event_id, total, seat_count, status)
                VALUES (%s,%s,%s,%s,'PENDING') RETURNING *
            """, (request.user_id, event_id, total, len(seats)))
            order = _serialize_row(cur.fetchone())
        conn.commit()

        order['seats'] = seats
        order['event_title'] = event.get('title', '')
        return jsonify(order), 201
    finally:
        conn.close()


@app.route('/api/orders/<int:order_id>/confirm', methods=['POST'])
@token_required
def confirm_order(order_id):
    """
    Confirma la orden: pago simulado, confirma asientos en Events Service,
    genera tickets.
    """
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            order = cur.fetchone()

        if not order:
            return jsonify({'error': 'Orden no encontrada'}), 404
        if order['user_id'] != request.user_id:
            return jsonify({'error': 'No autorizado'}), 403
        if order['status'] != 'PENDING':
            return jsonify({'error': 'La orden ya fue procesada'}), 400

        # Obtener asientos en HOLD de este usuario para este evento
        try:
            resp = http_requests.get(
                f'{EVENTS_SERVICE_URL}/api/events/{order["event_id"]}/seats',
                timeout=5
            )
            seat_data = resp.json()
        except Exception as e:
            return jsonify({'error': f'Error obteniendo mapa de asientos: {str(e)}'}), 500

        user_held_seats = []
        now = datetime.datetime.utcnow()
        for seat_id, seat in seat_data.get('seats', {}).items():
            if seat['status'] == 'HELD' and seat.get('held_by') == request.user_id:
                # Verificar que no haya expirado
                if seat.get('hold_until'):
                    hold_dt = seat['hold_until']
                    if isinstance(hold_dt, str):
                        hold_dt = datetime.datetime.fromisoformat(hold_dt.replace('Z', ''))
                    if hold_dt < now:
                        continue
                user_held_seats.append(seat_id)

        if not user_held_seats:
            # Cancelar orden
            with conn.cursor() as cur:
                cur.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = %s", (order_id,))
            conn.commit()
            return jsonify({'error': 'No hay asientos en HOLD. La reserva pudo haber expirado.'}), 400

        # ── Pago simulado ──
        # (Aquí iría la integración con pasarela de pago real)
        payment_ok = True

        if not payment_ok:
            return jsonify({'error': 'Error en el pago'}), 402

        # ── Confirmar asientos en Events Service ──
        try:
            resp = http_requests.post(
                f'{EVENTS_SERVICE_URL}/api/events/{order["event_id"]}/confirm-seats',
                json={'seats': user_held_seats, 'user_id': request.user_id},
                headers={'Authorization': f'Bearer {request.token_raw}'},
                timeout=5
            )
        except Exception as e:
            return jsonify({'error': f'Error confirmando asientos: {str(e)}'}), 500

        # ── Generar tickets ──
        tickets = []
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for seat_id in user_held_seats:
                code = generate_ticket_code()
                cur.execute("""
                    INSERT INTO tickets (order_id, event_id, seat_id, code)
                    VALUES (%s,%s,%s,%s) RETURNING *
                """, (order_id, order['event_id'], seat_id, code))
                tickets.append(_serialize_row(cur.fetchone()))

            # Actualizar orden
            cur.execute(
                "UPDATE orders SET status = 'CONFIRMED', seat_count = %s, total = %s WHERE id = %s",
                (len(user_held_seats), float(order['total']), order_id)
            )
        conn.commit()

        audit(conn, request.user_id, 'CONFIRM_ORDER',
              f'Orden {order_id}, {len(tickets)} tickets, evento {order["event_id"]}')

        return jsonify({
            'message': '¡Compra confirmada con éxito!',
            'order_id': order_id,
            'tickets': tickets
        })
    finally:
        conn.close()


@app.route('/api/orders/my', methods=['GET'])
@token_required
def my_orders():
    """Lista las órdenes del usuario actual con sus tickets."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT o.*, e.title AS event_title, e.start_time AS event_date,
                       v.name AS venue_name
                FROM orders o
                JOIN events e ON o.event_id = e.id
                JOIN venues v ON e.venue_id = v.id
                WHERE o.user_id = %s
                ORDER BY o.created_at DESC
            """, (request.user_id,))
            orders = [_serialize_row(o) for o in cur.fetchall()]

            for order in orders:
                cur.execute(
                    "SELECT * FROM tickets WHERE order_id = %s ORDER BY seat_id",
                    (order['id'],)
                )
                order['tickets'] = [_serialize_row(t) for t in cur.fetchall()]

        return jsonify(orders)
    finally:
        conn.close()


@app.route('/api/orders/event/<int:event_id>', methods=['GET'])
@admin_required
def orders_by_event(event_id):
    """Admin: lista órdenes y tickets de un evento."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT o.*, u.email AS user_email, u.name AS user_name
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.event_id = %s
                ORDER BY o.created_at DESC
            """, (event_id,))
            orders = [_serialize_row(o) for o in cur.fetchall()]

            for order in orders:
                cur.execute(
                    "SELECT * FROM tickets WHERE order_id = %s ORDER BY seat_id",
                    (order['id'],)
                )
                order['tickets'] = [_serialize_row(t) for t in cur.fetchall()]

        return jsonify(orders)
    finally:
        conn.close()


# ── Main ───────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('ORDERS_PORT', 7002))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f"🎟️  Orders Service iniciando en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
