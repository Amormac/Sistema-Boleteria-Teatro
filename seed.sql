-- ============================================================
-- SEED: Datos iniciales del sistema
-- IMPORTANTE: Después de ejecutar este archivo, ejecutar:
--   python3 scripts/init_mongo.py
-- para regenerar el hash bcrypt correcto y crear los seat_maps.
-- ============================================================

-- Admin por defecto
-- Email: admin@teatro.com  /  Password: Admin123!
-- NOTA: Este hash es un placeholder. init_mongo.py lo regenera correctamente.
INSERT INTO users (email, password_hash, name, role)
VALUES (
    'admin@teatro.com',
    '$2b$12$placeholder.hash.will.be.replaced.by.init_mongo.py.script',
    'Administrador',
    'ADMIN'
) ON CONFLICT (email) DO NOTHING;

-- Sala demo: "Sala Principal" con 10 filas (A-J) y 15 columnas
INSERT INTO venues (name, rows_count, cols_count, image_main)
VALUES ('Sala Principal', 10, 15, 'https://images.unsplash.com/photo-1503095392237-7362402049e5?w=800&auto=format&fit=crop');

-- Evento demo: función de teatro
INSERT INTO events (venue_id, title, description, start_time, end_time, price, max_per_user, status)
VALUES (
    1,
    'El Fantasma de la Ópera',
    'Una noche mágica con la obra clásica de Andrew Lloyd Webber. Disfruta de una experiencia teatral inolvidable.',
    NOW() + INTERVAL '7 days',
    NOW() + INTERVAL '7 days' + INTERVAL '2 hours',
    15.00,
    4,
    'ACTIVE'
);

-- Registro en auditoría
INSERT INTO audit_log (user_id, action, detail)
VALUES (1, 'SEED', 'Carga inicial de datos: admin + sala + evento demo');
