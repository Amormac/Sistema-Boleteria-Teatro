-- ============================================================
-- SCHEMA: Sistema de Venta de Entradas para Teatro
-- Base de datos: PostgreSQL
-- ============================================================

-- Extensión para UUID (opcional, usamos SERIAL + código propio)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TABLA: users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name        VARCHAR(255) NOT NULL DEFAULT '',
    role        VARCHAR(20)  NOT NULL DEFAULT 'USER'
                CHECK (role IN ('USER', 'ADMIN')),
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);

-- ============================================================
-- TABLA: venues (salas)
-- ============================================================
CREATE TABLE IF NOT EXISTS venues (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    rows_count  INTEGER NOT NULL CHECK (rows_count > 0 AND rows_count <= 26),
    cols_count  INTEGER NOT NULL CHECK (cols_count > 0),
    image_main  TEXT DEFAULT '',
    image_gallery JSONB DEFAULT '[]'::jsonb,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLA: events (eventos)
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id            SERIAL PRIMARY KEY,
    venue_id      INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    title         VARCHAR(500) NOT NULL,
    description   TEXT DEFAULT '',
    start_time    TIMESTAMP NOT NULL,
    end_time      TIMESTAMP NOT NULL,
    price         NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    max_per_user  INTEGER NOT NULL DEFAULT 4,
    status        VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                  CHECK (status IN ('DRAFT', 'ACTIVE', 'CLOSED')),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_status ON events (status);
CREATE INDEX idx_events_venue  ON events (venue_id);

-- ============================================================
-- TABLA: orders (órdenes de compra)
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    event_id    INTEGER NOT NULL REFERENCES events(id),
    total       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    seat_count  INTEGER NOT NULL DEFAULT 0,
    status      VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_user  ON orders (user_id);
CREATE INDEX idx_orders_event ON orders (event_id);

-- ============================================================
-- TABLA: tickets (boletos generados)
-- ============================================================
CREATE TABLE IF NOT EXISTS tickets (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    event_id    INTEGER NOT NULL REFERENCES events(id),
    seat_id     VARCHAR(10) NOT NULL,
    code        VARCHAR(50) UNIQUE NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tickets_order ON tickets (order_id);
CREATE INDEX idx_tickets_event ON tickets (event_id);
CREATE INDEX idx_tickets_code  ON tickets (code);

-- ============================================================
-- TABLA: audit_log (registro de auditoría)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    action      VARCHAR(100) NOT NULL,
    detail      TEXT DEFAULT '',
    ip_address  VARCHAR(50) DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_action ON audit_log (action);
CREATE INDEX idx_audit_user   ON audit_log (user_id);
