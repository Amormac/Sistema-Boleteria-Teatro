#!/usr/bin/env bash
# ============================================================
# start_all.sh — Arranca los 4 microservicios del sistema
# Uso: bash scripts/start_all.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Cargar .env si existe
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "📄 Cargando variables de .env..."
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Verificar Python (preferir venv si existe)
if [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
    PYTHON="$PROJECT_DIR/venv/bin/python3"
elif [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

if [ -z "$PYTHON" ]; then
    echo "❌ Python3 no encontrado. Instálalo primero."
    exit 1
fi

echo "🐍 Usando: $PYTHON"
echo "📁 Proyecto: $PROJECT_DIR"
echo ""

# Detener servicios anteriores si existen
pkill -f 'services/.*/app\.py' 2>/dev/null || true
sleep 1

# Función para iniciar un servicio
start_service() {
    local name="$1"
    local path="$2"
    local port="$3"

    echo "🚀 Iniciando $name en puerto $port..."
    nohup "$PYTHON" "$PROJECT_DIR/$path" > "/tmp/teatro-${name}.log" 2>&1 &
    echo "   PID: $! → log en /tmp/teatro-${name}.log"
}

# Iniciar servicios
start_service "auth"    "services/auth/app.py"     "${AUTH_PORT:-7000}"
start_service "events"  "services/events/app.py"   "${SEATING_PORT:-7001}"
start_service "orders"  "services/orders/app.py"   "${ORDERS_PORT:-7002}"

# Esperar un momento para que los backends arranquen
sleep 2

start_service "gateway" "services/gateway/app.py"  "${WEB_PORT:-8080}"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Todos los servicios iniciados"
echo ""
echo "  🔐 Auth Service:     http://localhost:${AUTH_PORT:-7000}"
echo "  🎭 Events Service:   http://localhost:${SEATING_PORT:-7001}"
echo "  🎟️  Orders Service:   http://localhost:${ORDERS_PORT:-7002}"
echo "  🌐 Web (Frontend):   http://localhost:${WEB_PORT:-8080}"
echo ""
echo "  Para ver los logs:   tail -f /tmp/teatro-*.log"
echo "  Para detener todo:   pkill -f 'services/.*/app.py'"
echo "═══════════════════════════════════════════════════════"
