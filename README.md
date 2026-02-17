# 🎭 Sistema de Venta de Entradas para Teatro

Plataforma web para la venta de entradas con selección de asientos en tiempo real, construida con una arquitectura de microservicios ligera (sin Docker, sin Kubernetes).

## Arquitectura

```
┌───────────────────────────────────────────────────────┐
│  vm-app (pública)                                          │
│                                                            │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────┐   │
│  │ Auth Service  │  │ Events/Seating   │  │  Orders    │   │
│  │ :7000         │  │ :7001            │  │  :7002     │   │
│  └──────┬───────┘  └───────┬────────┘  └─────┬─────┘   │
│          │                   │                  │          │
│  ┌──────┴──────────────────┴────────────────┴─────┐    │
│  │           Web Gateway / Frontend :8080             │    │
│  └───────────────────────┬────────────────────────┘    │
│                            │ (HTTP interno)                │
└──────────────────────────┼────────────────────────────┘
                              │
┌──────────────────────────┼────────────────────────────┐
│  vm-db (privada)           │                               │
│                            │                               │
│  ┌─────────────┐    ┌────┴────────┐                     │
│  │ PostgreSQL   │    │  MongoDB     │                      │
│  │ :5432        │    │  :27017      │                      │
│  └─────────────┘    └─────────────┘                     │
└───────────────────────────────────────────────────────┘
```

| Servicio | Puerto | Base de Datos | Función |
|----------|--------|---------------|---------|
| Auth Service | 7000 | PostgreSQL | Registro, login, JWT |
| Events & Seating | 7001 | PostgreSQL + MongoDB | Salas, eventos, mapa de asientos |
| Orders Service | 7002 | PostgreSQL | Órdenes, tickets |
| Web Gateway | 8080 | — | Frontend HTML, proxy a servicios |

## Tecnologías

- **Backend**: Python 3 + Flask
- **Frontend**: HTML5 + CSS3 + JavaScript (Vanilla)
- **Auth**: JWT + bcrypt
- **PostgreSQL**: Usuarios, salas, eventos, órdenes, tickets, auditoría
- **MongoDB**: Mapas de asientos con operaciones atómicas

---

## Estructura del Repositorio

```
├── .env.example              # Variables de entorno (plantilla)
├── .gitignore
├── requirements.txt          # Dependencias Python (todas)
├── schema_postgres.sql       # Schema de PostgreSQL
├── seed.sql                  # Datos iniciales (admin + sala + evento)
├── scripts/
│   ├── init_mongo.py         # Inicializa MongoDB + contraseña admin
│   └── start_all.sh          # Arranca los 4 servicios
├── systemd/                  # Archivos de servicio systemd
│   ├── teatro-auth.service
│   ├── teatro-events.service
│   ├── teatro-orders.service
│   └── teatro-gateway.service
└── services/
    ├── auth/                 # Auth Service
    │   ├── app.py
    │   └── requirements.txt
    ├── events/               # Events & Seating Service
    │   ├── app.py
    │   └── requirements.txt
    ├── orders/               # Orders Service
    │   ├── app.py
    │   └── requirements.txt
    └── gateway/              # Web Gateway / Frontend
        ├── app.py
        ├── requirements.txt
        ├── templates/
        │   ├── base.html
        │   ├── index.html
        │   ├── login.html
        │   ├── register.html
        │   ├── event_detail.html
        │   ├── my_tickets.html
        │   └── admin/
        │       ├── dashboard.html
        │       ├── venues.html
        │       ├── events.html
        │       └── event_sales.html
        └── static/
            ├── css/style.css
            └── js/
                ├── app.js
                └── seating.js
```

---

## Instalación y Despliegue en Azure (2 VMs)

### Requisitos previos

- 2 VMs Ubuntu 22.04 / Debian 12 en Azure
- VNet con 2 subredes:
  - `subnet-app` (ej: `10.10.1.0/28`) — vm-app con IP pública
  - `subnet-db` (ej: `10.10.2.0/28`) — vm-db SIN IP pública
- NSG de vm-db: solo TCP 5432 y 27017 desde `subnet-app`

### 1. Configurar vm-db (base de datos)

SSH a vm-db (a través de vm-app como jump host):

```bash
# Desde tu máquina local, saltar por vm-app:
ssh -J azureuser@<IP_PUBLICA_VM_APP> azureuser@<IP_PRIVADA_VM_DB>
```

#### Instalar PostgreSQL

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib

# Crear usuario y base de datos
sudo -u postgres psql -c "CREATE USER teatro WITH PASSWORD 'teatro_password_seguro';"
sudo -u postgres psql -c "CREATE DATABASE teatro OWNER teatro;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE teatro TO teatro;"
```

Editar `/etc/postgresql/*/main/postgresql.conf`:
```
listen_addresses = '*'
```

Editar `/etc/postgresql/*/main/pg_hba.conf` (agregar al final):
```
host    teatro    teatro    10.10.1.0/28    md5
```

```bash
sudo systemctl restart postgresql
```

#### Instalar MongoDB

```bash
# Para Ubuntu 22.04:
sudo apt install -y gnupg curl
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update && sudo apt install -y mongodb-org
```

Editar `/etc/mongod.conf`:
```yaml
net:
  port: 27017
  bindIp: 0.0.0.0
```

```bash
sudo systemctl enable --now mongod
```

### 2. Configurar vm-app (aplicación)

```bash
ssh azureuser@<IP_PUBLICA_VM_APP>
```

#### Instalar dependencias

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

#### Clonar/copiar el proyecto

```bash
# Opción A: clonar desde Git
git clone <URL_DEL_REPO> ~/teatro
cd ~/teatro

# Opción B: copiar con scp desde tu máquina
# scp -r ./APLICACION/ azureuser@<IP_PUBLICA>:~/teatro
```

#### Configurar entorno Python

```bash
cd ~/teatro
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Editar `.env` con los valores reales:
```env
JWT_SECRET=una-clave-secreta-larga-y-aleatoria-aqui
FLASK_SECRET=otra-clave-secreta-para-cookies

POSTGRES_HOST=<IP_PRIVADA_VM_DB>
POSTGRES_PORT=5432
POSTGRES_DB=teatro
POSTGRES_USER=teatro
POSTGRES_PASS=teatro_password_seguro

MONGO_URI=mongodb://<IP_PRIVADA_VM_DB>:27017
MONGO_DB=teatro
```

#### Ejecutar schema SQL y seed

```bash
# Desde vm-app, conectar a PostgreSQL en vm-db:
PGPASSWORD=teatro_password_seguro psql -h <IP_PRIVADA_VM_DB> -U teatro -d teatro -f schema_postgres.sql
PGPASSWORD=teatro_password_seguro psql -h <IP_PRIVADA_VM_DB> -U teatro -d teatro -f seed.sql
```

#### Inicializar MongoDB y contraseña admin

```bash
source venv/bin/activate
python3 scripts/init_mongo.py
```

Esto:
- Regenera el hash bcrypt del admin en PostgreSQL
- Crea el mapa de asientos en MongoDB para el evento demo

#### Arrancar servicios (modo manual)

```bash
bash scripts/start_all.sh
```

#### Arrancar servicios (modo systemd — recomendado)

```bash
# Copiar archivos de servicio
sudo cp systemd/teatro-*.service /etc/systemd/system/

# Si tu usuario no es "azureuser" o la ruta no es /home/azureuser/teatro,
# edita los archivos .service para ajustar User, WorkingDirectory y ExecStart.

# Recargar systemd
sudo systemctl daemon-reload

# Habilitar e iniciar servicios
sudo systemctl enable --now teatro-auth
sudo systemctl enable --now teatro-events
sudo systemctl enable --now teatro-orders
sudo systemctl enable --now teatro-gateway

# Verificar estado
sudo systemctl status teatro-auth teatro-events teatro-orders teatro-gateway
```

### 3. Acceder al sistema

#### Desde tu laptop (SSH Tunnel)

```bash
ssh -L 8080:<IP_PRIVADA_VM_APP>:8080 azureuser@<IP_PUBLICA_VM_APP>
```

Luego abre en el navegador: **http://localhost:8080**

#### Si vm-app tiene IP pública y el puerto 8080 está abierto en el NSG:

Abre directamente: `http://<IP_PUBLICA_VM_APP>:8080`

---

## Credenciales por defecto

| Rol | Email | Contraseña |
|-----|-------|------------|
| Admin | admin@teatro.com | Admin123! |

> ⚠️ Cambia la contraseña del admin en producción.

---

## Datos de demostración

El seed incluye:
- **Usuario admin**: `admin@teatro.com` / `Admin123!`
- **Sala**: "Sala Principal" — 10 filas (A-J) × 15 columnas = 150 asientos
- **Evento**: "El Fantasma de la Ópera" — dentro de 7 días, $15.00, máx 4 boletos

---

## Uso del Sistema

### Como usuario (comprador)

1. Regístrate o inicia sesión
2. En la página principal, ve los eventos disponibles
3. Haz clic en "Ver asientos y comprar"
4. Selecciona tus asientos en el mapa (los libres son verdes)
5. Presiona "🔒 Reservar (10 min)" — los asientos se mantienen por 10 minutos
6. Presiona "✅ Confirmar Compra" — pago simulado, se generan tus tickets
7. Ve tus tickets en "Mis Tickets"

### Como administrador

1. Inicia sesión con la cuenta admin
2. Ve al "Panel Admin" desde la barra de navegación
3. **Salas**: crea nuevas salas con filas/columnas
4. **Eventos**: crea eventos, asócialos a una sala, define precio y límite
5. **Activar evento**: cambia estado de DRAFT → ACTIVE para publicarlo
6. **Ver ventas**: consulta estadísticas y tickets vendidos
7. **Cerrar evento**: cambia estado a CLOSED cuando finalice

---

## Reglas de negocio

- **HOLD temporal**: 10 minutos de reserva antes de confirmar
- **Concurrencia**: operaciones atómicas en MongoDB (`findOneAndUpdate`)
- **Límite por usuario**: configurable por evento (campo `max_per_user`)
- **Expiración automática**: hilo en background libera holds cada 30 segundos
- **Tickets**: código único `TCK-XXXXXXXX` por asiento confirmado
- **Zonas**: campo `zone` preparado para GENERAL/VIP (futuro)

---

## Solución de problemas

```bash
# Ver logs de un servicio específico
sudo journalctl -u teatro-auth -f
sudo journalctl -u teatro-events -f
sudo journalctl -u teatro-orders -f
sudo journalctl -u teatro-gateway -f

# O si se inició con start_all.sh:
tail -f /tmp/teatro-auth.log
tail -f /tmp/teatro-events.log

# Verificar que los puertos estén escuchando
ss -tlnp | grep -E '7000|7001|7002|8080'

# Probar conexión a PostgreSQL desde vm-app
PGPASSWORD=teatro_password_seguro psql -h <IP_VM_DB> -U teatro -d teatro -c "SELECT COUNT(*) FROM users;"

# Probar conexión a MongoDB desde vm-app
mongosh mongodb://<IP_VM_DB>:27017/teatro --eval "db.seat_maps.countDocuments()"

# Reiniciar todos los servicios
sudo systemctl restart teatro-auth teatro-events teatro-orders teatro-gateway

# Detener servicios manuales
pkill -f 'services/.*/app.py'
```

---

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `JWT_SECRET` | `super-secret-key-change-me` | Clave secreta para tokens JWT |
| `FLASK_SECRET` | `flask-secret-change-me` | Clave para cookies de sesión |
| `FLASK_DEBUG` | `false` | Modo debug de Flask |
| `AUTH_PORT` | `7000` | Puerto del Auth Service |
| `SEATING_PORT` | `7001` | Puerto del Events Service |
| `ORDERS_PORT` | `7002` | Puerto del Orders Service |
| `WEB_PORT` | `8080` | Puerto del Gateway/Frontend |
| `AUTH_SERVICE_URL` | `http://localhost:7000` | URL interna del Auth Service |
| `EVENTS_SERVICE_URL` | `http://localhost:7001` | URL interna del Events Service |
| `ORDERS_SERVICE_URL` | `http://localhost:7002` | URL interna del Orders Service |
| `POSTGRES_HOST` | `localhost` | Host de PostgreSQL |
| `POSTGRES_PORT` | `5432` | Puerto de PostgreSQL |
| `POSTGRES_DB` | `teatro` | Nombre de la BD |
| `POSTGRES_USER` | `teatro` | Usuario de la BD |
| `POSTGRES_PASS` | `teatro123` | Contraseña de la BD |
| `MONGO_URI` | `mongodb://localhost:27017` | URI de conexión MongoDB |
| `MONGO_DB` | `teatro` | Nombre de la BD en Mongo |
