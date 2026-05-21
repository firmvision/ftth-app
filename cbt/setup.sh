#!/usr/bin/env bash
# Firmvision CBT Platform — Automated Server Setup
# Supports Ubuntu 20.04/22.04/24.04 and Debian 11/12
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()   { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="cbt-exam"
APP_PORT=8000
NGINX_AVAILABLE="/etc/nginx/sites-available/$SERVICE_NAME"
NGINX_ENABLED="/etc/nginx/sites-enabled/$SERVICE_NAME"

banner() {
cat <<'BANNER'
╔══════════════════════════════════════════════════════════╗
║         Firmvision CBT Platform — Server Setup           ║
║         © 2026 Firmvision Technologies Ltd               ║
╚══════════════════════════════════════════════════════════╝
BANNER
}

check_root() {
    [[ $EUID -eq 0 ]] || die "Run this script as root: sudo bash setup.sh"
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID="$ID"; OS_VER="$VERSION_ID"
        info "Detected OS: $PRETTY_NAME"
    else
        die "Cannot detect OS. /etc/os-release not found."
    fi
    case "$OS_ID" in
        ubuntu|debian) ok "Supported OS." ;;
        *) warn "Untested OS '$OS_ID' — proceeding anyway." ;;
    esac
}

install_system_deps() {
    info "Updating package lists..."
    apt-get update -q
    info "Installing system dependencies..."
    apt-get install -y -q \
        python3 python3-pip python3-venv python3-dev \
        nginx \
        postgresql postgresql-contrib \
        libpq-dev \
        curl wget git \
        ufw \
        build-essential \
        libxml2-dev libxslt1-dev libffi-dev libssl-dev \
        weasyprint
    ok "System dependencies installed."
}

setup_postgres() {
    info "Configuring PostgreSQL..."
    systemctl enable postgresql
    systemctl start postgresql

    DB_NAME="cbt_exam"
    DB_USER="cbt"
    DB_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)

    # Create user and database (idempotent)
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

    echo "$DB_PASS" > /tmp/cbt_db_pass.tmp
    ok "PostgreSQL configured. DB: $DB_NAME, User: $DB_USER"
}

generate_env() {
    info "Generating .env file..."
    DB_PASS=$(cat /tmp/cbt_db_pass.tmp)
    rm -f /tmp/cbt_db_pass.tmp

    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    ADMIN_PASS=$(python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(16)))")

    cat > "$APP_DIR/backend/.env" <<ENV
# Firmvision CBT — Environment Configuration
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
DATABASE_URL=postgresql://cbt:${DB_PASS}@localhost:5432/cbt_exam
SECRET_KEY=${SECRET_KEY}
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASS}
CORS_ORIGINS=*
TOKEN_EXPIRE_HOURS=8
ENV

    chmod 600 "$APP_DIR/backend/.env"
    ok "Generated .env with secure secrets."

    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════╗"
    echo -e "║          SAVE THESE CREDENTIALS NOW              ║"
    echo -e "╠══════════════════════════════════════════════════╣"
    echo -e "║  Admin Username : admin                          ║"
    echo -e "║  Admin Password : ${ADMIN_PASS}   ║"
    echo -e "╚══════════════════════════════════════════════════╝${NC}"
    echo ""
}

setup_venv() {
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$APP_DIR/backend/requirements.txt" -q
    ok "Python venv ready at $VENV_DIR"
}

create_static_dir() {
    info "Setting up static file directory..."
    mkdir -p "$APP_DIR/static"
    cp "$APP_DIR/login.html"   "$APP_DIR/static/login.html"
    cp "$APP_DIR/admin.html"   "$APP_DIR/static/admin.html"
    cp "$APP_DIR/student.html" "$APP_DIR/static/student.html"
    ok "Static files copied."
}

setup_systemd() {
    info "Creating systemd service: $SERVICE_NAME..."
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Firmvision CBT Exam Platform
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}/backend
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${VENV_DIR}/bin/uvicorn main:app --host 127.0.0.1 --port ${APP_PORT} --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
UNIT

    chown -R www-data:www-data "$APP_DIR"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
    ok "Systemd service '$SERVICE_NAME' enabled and started."
}

setup_nginx() {
    local domain="${1:-_}"
    info "Configuring nginx (server_name: $domain)..."

    cat > "$NGINX_AVAILABLE" <<NGINX
server {
    listen 80;
    server_name ${domain};

    client_max_body_size 20M;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
    }

    # Static HTML — serve directly
    location ~* \.(html|css|js|ico|png|jpg|svg)$ {
        proxy_pass http://127.0.0.1:${APP_PORT};
        expires 1h;
        add_header Cache-Control "public";
    }

    access_log /var/log/nginx/${SERVICE_NAME}-access.log;
    error_log  /var/log/nginx/${SERVICE_NAME}-error.log;
}
NGINX

    ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    ok "Nginx configured."
}

setup_firewall() {
    info "Configuring UFW firewall..."
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    ok "Firewall configured (SSH + HTTP + HTTPS)."
}

print_summary() {
    local ip
    ip=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗"
    echo -e "║              Setup Complete! 🎉                          ║"
    echo -e "╠══════════════════════════════════════════════════════════╣"
    echo -e "║  Application URL : http://${ip}                   "
    echo -e "║  API Health      : http://${ip}/api/health        "
    echo -e "║  Service status  : systemctl status ${SERVICE_NAME}        "
    echo -e "║  Logs            : journalctl -u ${SERVICE_NAME} -f        "
    echo -e "╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    warn "For HTTPS, run: certbot --nginx -d your-domain.com"
}

main() {
    banner
    check_root
    detect_os

    DOMAIN="${1:-_}"

    install_system_deps
    setup_postgres
    generate_env
    setup_venv
    create_static_dir
    setup_systemd
    setup_nginx "$DOMAIN"
    setup_firewall
    print_summary
}

main "$@"
