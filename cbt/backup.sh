#!/usr/bin/env bash
# Firmvision CBT Platform — Backup & Restore Script
# Usage: ./backup.sh [backup|restore] [--file <path>]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()   { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_NAME="${DB_NAME:-cbt_exam}"
DB_USER="${DB_USER:-cbt}"
SERVICE_NAME="cbt-exam"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

banner() {
cat <<'BANNER'
╔══════════════════════════════════════════════════════════╗
║         Firmvision CBT Platform — Backup Tool            ║
╚══════════════════════════════════════════════════════════╝
BANNER
}

load_env() {
    if [[ -f "$APP_DIR/backend/.env" ]]; then
        export $(grep -v '^#' "$APP_DIR/backend/.env" | xargs)
        ok "Loaded .env"
    else
        warn ".env not found — using environment variables or defaults."
    fi
    # Parse DATABASE_URL if set
    if [[ -n "${DATABASE_URL:-}" ]]; then
        # postgresql://user:pass@host:port/dbname
        DB_USER=$(echo "$DATABASE_URL" | sed 's|.*://\([^:]*\):.*|\1|')
        DB_PASS=$(echo "$DATABASE_URL" | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|')
        DB_HOST=$(echo "$DATABASE_URL" | sed 's|.*@\([^:]*\):.*|\1|')
        DB_PORT=$(echo "$DATABASE_URL" | sed 's|.*:\([0-9]*\)/.*|\1|')
        DB_NAME=$(echo "$DATABASE_URL" | sed 's|.*/\([^?]*\).*|\1|')
        export PGPASSWORD="$DB_PASS"
    fi
}

do_backup() {
    mkdir -p "$BACKUP_DIR"
    local BACKUP_FILE="$BACKUP_DIR/cbt_backup_${TIMESTAMP}.tar.gz"
    local DB_DUMP="$BACKUP_DIR/db_${TIMESTAMP}.sql"

    info "Backing up PostgreSQL database '$DB_NAME'..."
    if pg_dump -U "$DB_USER" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" "$DB_NAME" > "$DB_DUMP" 2>/dev/null; then
        ok "Database dump: $DB_DUMP"
    else
        warn "PostgreSQL dump failed — checking for SQLite..."
        SQLITE_DB=$(find "$APP_DIR/backend" -name "*.db" 2>/dev/null | head -1)
        if [[ -n "$SQLITE_DB" ]]; then
            cp "$SQLITE_DB" "$BACKUP_DIR/sqlite_${TIMESTAMP}.db"
            ok "SQLite copied: $BACKUP_DIR/sqlite_${TIMESTAMP}.db"
            DB_DUMP="$BACKUP_DIR/sqlite_${TIMESTAMP}.db"
        else
            die "No database found to back up."
        fi
    fi

    info "Creating archive..."
    tar -czf "$BACKUP_FILE" \
        -C "$BACKUP_DIR" "$(basename "$DB_DUMP")" \
        -C "$APP_DIR" \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git' \
        --exclude='backups' \
        backend/ login.html admin.html student.html \
        2>/dev/null || true

    # Clean up loose dump file
    rm -f "$DB_DUMP"

    local SIZE
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    ok "Backup created: $BACKUP_FILE ($SIZE)"

    # Retention: remove backups older than RETENTION_DAYS
    info "Applying $RETENTION_DAYS-day retention policy..."
    find "$BACKUP_DIR" -name "cbt_backup_*.tar.gz" -mtime "+$RETENTION_DAYS" -exec rm -f {} \; -exec echo "Removed: {}" \;

    local COUNT
    COUNT=$(find "$BACKUP_DIR" -name "cbt_backup_*.tar.gz" | wc -l)
    ok "$COUNT backup(s) retained in $BACKUP_DIR"

    echo ""
    echo -e "${GREEN}Backup complete: $BACKUP_FILE${NC}"
}

do_restore() {
    local RESTORE_FILE="${1:-}"
    if [[ -z "$RESTORE_FILE" ]]; then
        # Find latest backup
        RESTORE_FILE=$(find "$BACKUP_DIR" -name "cbt_backup_*.tar.gz" | sort | tail -1)
        [[ -n "$RESTORE_FILE" ]] || die "No backup file found. Use --file <path>"
        info "Auto-selected latest backup: $RESTORE_FILE"
    fi

    [[ -f "$RESTORE_FILE" ]] || die "Backup file not found: $RESTORE_FILE"

    echo -e "${YELLOW}WARNING: This will overwrite the current database and application files.${NC}"
    read -r -p "Type 'yes' to confirm restore: " CONFIRM
    [[ "$CONFIRM" == "yes" ]] || die "Restore cancelled."

    local RESTORE_TMP="/tmp/cbt_restore_${TIMESTAMP}"
    mkdir -p "$RESTORE_TMP"

    info "Extracting archive..."
    tar -xzf "$RESTORE_FILE" -C "$RESTORE_TMP"

    # Stop service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Stopping $SERVICE_NAME..."
        systemctl stop "$SERVICE_NAME"
    fi

    # Restore database
    local SQL_DUMP
    SQL_DUMP=$(find "$RESTORE_TMP" -name "db_*.sql" | head -1)
    if [[ -n "$SQL_DUMP" ]]; then
        info "Restoring PostgreSQL database..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};"
        sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
        psql -U "$DB_USER" -h "${DB_HOST:-localhost}" "$DB_NAME" < "$SQL_DUMP"
        ok "Database restored."
    fi

    # Restore SQLite if present
    local SQLITE_DUMP
    SQLITE_DUMP=$(find "$RESTORE_TMP" -name "sqlite_*.db" | head -1)
    if [[ -n "$SQLITE_DUMP" ]]; then
        info "Restoring SQLite database..."
        DEST=$(find "$APP_DIR/backend" -name "*.db" | head -1)
        [[ -n "$DEST" ]] || DEST="$APP_DIR/backend/cbt_exam.db"
        cp "$SQLITE_DUMP" "$DEST"
        ok "SQLite database restored to $DEST"
    fi

    # Restore application files
    if [[ -d "$RESTORE_TMP/backend" ]]; then
        info "Restoring backend files..."
        rsync -a --exclude='.env' "$RESTORE_TMP/backend/" "$APP_DIR/backend/"
        ok "Backend files restored (env preserved)."
    fi

    for f in login.html admin.html student.html; do
        [[ -f "$RESTORE_TMP/$f" ]] && cp "$RESTORE_TMP/$f" "$APP_DIR/$f" && ok "Restored $f"
    done

    # Clean up
    rm -rf "$RESTORE_TMP"

    # Restart service
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Restarting $SERVICE_NAME..."
        systemctl start "$SERVICE_NAME"
        sleep 2
        systemctl is-active --quiet "$SERVICE_NAME" && ok "$SERVICE_NAME running." || warn "$SERVICE_NAME failed to start — check logs."
    fi

    ok "Restore complete from: $RESTORE_FILE"
}

list_backups() {
    if [[ ! -d "$BACKUP_DIR" ]] || [[ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]]; then
        info "No backups found in $BACKUP_DIR"
        return
    fi
    echo ""
    echo -e "${BLUE}Available backups in $BACKUP_DIR:${NC}"
    find "$BACKUP_DIR" -name "cbt_backup_*.tar.gz" | sort | while read -r f; do
        local SIZE DATE_STR
        SIZE=$(du -sh "$f" | cut -f1)
        DATE_STR=$(basename "$f" | sed 's/cbt_backup_\([0-9]*\)_\([0-9]*\)\.tar\.gz/\1 \2/' | \
                   awk '{print substr($1,1,4)"-"substr($1,5,2)"-"substr($1,7,2)" "substr($2,1,2)":"substr($2,3,2)":"substr($2,5,2)}')
        printf "  %-50s  %6s  %s\n" "$(basename "$f")" "$SIZE" "$DATE_STR"
    done
    echo ""
}

install_cron() {
    local SCHEDULE="${1:-0 2 * * *}"  # Default: 2 AM daily
    local CRON_CMD="$SCHEDULE cd $APP_DIR && bash backup.sh backup >> $BACKUP_DIR/cron.log 2>&1"
    (crontab -l 2>/dev/null | grep -v "backup.sh"; echo "$CRON_CMD") | crontab -
    ok "Cron job installed: $SCHEDULE"
    info "Logs will appear in $BACKUP_DIR/cron.log"
}

usage() {
    cat <<USAGE
Firmvision CBT — Backup & Restore

Usage:
  ./backup.sh backup              Create a new backup
  ./backup.sh restore             Restore from latest backup
  ./backup.sh restore --file PATH Restore from specific backup file
  ./backup.sh list                List all backups
  ./backup.sh cron [SCHEDULE]     Install daily cron job
                                  Default schedule: "0 2 * * *" (2 AM daily)

Environment Variables:
  BACKUP_DIR      Directory to store backups (default: ./backups)
  RETENTION_DAYS  Days to keep backups (default: 30)
  DB_NAME         Database name (default: cbt_exam)
  DB_USER         Database user (default: cbt)

Examples:
  ./backup.sh backup
  ./backup.sh restore --file backups/cbt_backup_20260520_020000.tar.gz
  ./backup.sh cron "0 1 * * *"   # Run at 1 AM daily
USAGE
}

main() {
    banner
    load_env

    local CMD="${1:-backup}"
    case "$CMD" in
        backup)
            do_backup
            ;;
        restore)
            local FILE=""
            [[ "${2:-}" == "--file" ]] && FILE="${3:-}"
            do_restore "$FILE"
            ;;
        list)
            list_backups
            ;;
        cron)
            install_cron "${2:-0 2 * * *}"
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
