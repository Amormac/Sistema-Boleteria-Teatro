#!/usr/bin/env python3
"""
init_mongo.py — Inicializa la colección seat_maps en MongoDB
para el evento demo (ID=1) creado por seed.sql.

También regenera la contraseña del admin en PostgreSQL.

Uso:
    python3 scripts/init_mongo.py
"""

import os
import sys
import bcrypt
import psycopg2
import psycopg2.extras
from pymongo import MongoClient
from dotenv import load_dotenv

# Cargar .env del proyecto
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
POSTGRES_DB   = os.environ.get('POSTGRES_DB', 'teatro')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'teatro')
POSTGRES_PASS = os.environ.get('POSTGRES_PASS', 'teatro123')

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
MONGO_DB  = os.environ.get('MONGO_DB', 'teatro')

ADMIN_EMAIL    = 'admin@teatro.com'
ADMIN_PASSWORD = 'Admin123!'


def init_admin_password():
    """Regenera el hash bcrypt del admin en PostgreSQL."""
    print("🔐 Regenerando contraseña del admin...")
    pw_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')

    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        database=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS
    )
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (pw_hash, ADMIN_EMAIL))
        if cur.rowcount == 0:
            # Insertar si no existe
            cur.execute(
                "INSERT INTO users (email, password_hash, name, role) VALUES (%s, %s, 'Administrador', 'ADMIN')",
                (ADMIN_EMAIL, pw_hash)
            )
    conn.commit()
    conn.close()
    print(f"   ✅ Admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


def init_seat_maps():
    """Crea los seat_maps en MongoDB para todos los eventos que no tengan uno."""
    print("🎭 Inicializando mapas de asientos en MongoDB...")

    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        database=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS
    )

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    seat_maps = db['seat_maps']

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT e.id AS event_id, e.title, v.id AS venue_id, v.name AS venue_name,
                   v.rows_count, v.cols_count
            FROM events e JOIN venues v ON e.venue_id = v.id
        """)
        events = cur.fetchall()

    for event in events:
        existing = seat_maps.find_one({'event_id': event['event_id']})
        if existing:
            print(f"   ⏭️  Evento {event['event_id']} ({event['title']}) ya tiene mapa.")
            continue

        seats = {}
        for r in range(event['rows_count']):
            row_letter = chr(65 + r)
            for c in range(1, event['cols_count'] + 1):
                seat_id = f"{row_letter}{c}"
                seats[seat_id] = {
                    'status': 'FREE',
                    'zone': 'GENERAL',
                    'held_by': None,
                    'hold_until': None
                }

        seat_maps.insert_one({
            'event_id': event['event_id'],
            'venue_id': event['venue_id'],
            'venue_name': event['venue_name'],
            'rows': event['rows_count'],
            'cols': event['cols_count'],
            'seats': seats
        })
        total = event['rows_count'] * event['cols_count']
        print(f"   ✅ Evento {event['event_id']} ({event['title']}): {total} asientos creados.")

    conn.close()
    client.close()


if __name__ == '__main__':
    try:
        init_admin_password()
        init_seat_maps()
        print("\n🎉 Inicialización completada con éxito.")
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
