import os
import psycopg2
from psycopg2 import sql

# Load env vars from .env file directly if available
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_NAME = os.getenv('POSTGRES_DB', 'teatrodb')
DB_USER = os.getenv('POSTGRES_USER', 'teatro_user')
DB_PASS = os.getenv('POSTGRES_PASS', 'Teatro1234')

def get_conn():
    print(f"Connecting to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        print("Connected successfully.")
        return conn
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        raise

def add_column_if_not_exists(cur, table, column, definition):
    try:
        cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {};").format(
            sql.Identifier(table),
            sql.Identifier(column),
            sql.SQL(definition)
        ))
        print(f"Added column {column} to {table}.")
    except psycopg2.errors.DuplicateColumn:
        print(f"Column {column} already exists in {table}.")
    except Exception as e:
        print(f"Error adding {column} to {table}: {e}")

def main():
    try:
        conn = get_conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            # Venues: image_main and image_gallery
            add_column_if_not_exists(cur, 'venues', 'image_main', "TEXT DEFAULT ''")
            add_column_if_not_exists(cur, 'venues', 'image_gallery', "JSONB DEFAULT '[]'::jsonb")
            
            # Events: end_time
            # For end_time, we need a default ensuring NOT NULL constraint holds if table has data.
            # We'll first add it as nullable, populate it, then set not null.
            try:
                cur.execute("ALTER TABLE events ADD COLUMN end_time TIMESTAMP;")
                print("Added column end_time to events.")
                cur.execute("UPDATE events SET end_time = start_time + INTERVAL '2 hours' WHERE end_time IS NULL;")
                print("Populated end_time for existing events.")
                cur.execute("ALTER TABLE events ALTER COLUMN end_time SET NOT NULL;")
                print("Set end_time to NOT NULL.")
            except psycopg2.errors.DuplicateColumn:
                print("Column end_time already exists in events.")
            except Exception as e:
                print(f"Error handling end_time: {e}")

        conn.close()
        print("Schema update completed.")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    main()
