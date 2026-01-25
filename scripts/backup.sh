#!/bin/bash
# =============================================================================
# Railway PostgreSQL Backup Script
# =============================================================================
# Crea backups comprimidos de PostgreSQL y variables de entorno
# Guarda en GitHub repo privado con rotación automática de 14 días
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------
BACKUP_RETENTION_DAYS=14
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="backups"
DB_BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
ENV_BACKUP_FILE="${BACKUP_DIR}/env_${TIMESTAMP}.enc"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date +"%Y-%m-%d %H:%M:%S") - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date +"%Y-%m-%d %H:%M:%S") - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date +"%Y-%m-%d %H:%M:%S") - $1"
}

# -----------------------------------------------------------------------------
# Validar variables de entorno requeridas
# -----------------------------------------------------------------------------
validate_env() {
    log_info "Validando variables de entorno..."

    local required_vars=("DATABASE_URL" "BACKUP_ENCRYPTION_KEY")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Variables de entorno faltantes: ${missing_vars[*]}"
        exit 1
    fi

    log_info "Variables de entorno validadas correctamente"
}

# -----------------------------------------------------------------------------
# Crear directorio de backups si no existe
# -----------------------------------------------------------------------------
setup_backup_dir() {
    log_info "Configurando directorio de backups..."

    if [[ ! -d "$BACKUP_DIR" ]]; then
        mkdir -p "$BACKUP_DIR"
        log_info "Directorio $BACKUP_DIR creado"
    fi

    # Crear .gitkeep para mantener el directorio en git
    touch "${BACKUP_DIR}/.gitkeep"
}

# -----------------------------------------------------------------------------
# Backup de PostgreSQL
# -----------------------------------------------------------------------------
backup_database() {
    log_info "Iniciando backup de PostgreSQL..."

    # Parsear DATABASE_URL para extraer componentes
    # Formato: postgresql://user:password@host:port/database
    if [[ "$DATABASE_URL" =~ ^postgres(ql)?://([^:]+):([^@]+)@([^:]+):([0-9]+)/(.+)$ ]]; then
        DB_USER="${BASH_REMATCH[2]}"
        DB_PASS="${BASH_REMATCH[3]}"
        DB_HOST="${BASH_REMATCH[4]}"
        DB_PORT="${BASH_REMATCH[5]}"
        DB_NAME="${BASH_REMATCH[6]}"

        # Remover parámetros de query string si existen
        DB_NAME="${DB_NAME%%\?*}"
    else
        log_error "No se pudo parsear DATABASE_URL"
        exit 1
    fi

    log_info "Conectando a: $DB_HOST:$DB_PORT/$DB_NAME"

    # Ejecutar pg_dump con compresión gzip
    PGPASSWORD="$DB_PASS" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-owner \
        --no-acl \
        --clean \
        --if-exists \
        --verbose \
        2>/dev/null | gzip -9 > "$DB_BACKUP_FILE"

    # Verificar que el archivo se creó correctamente
    if [[ -f "$DB_BACKUP_FILE" ]] && [[ -s "$DB_BACKUP_FILE" ]]; then
        local size=$(du -h "$DB_BACKUP_FILE" | cut -f1)
        log_info "Backup de base de datos completado: $DB_BACKUP_FILE ($size)"
    else
        log_error "Error al crear backup de base de datos"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Backup de variables de entorno (encriptado)
# -----------------------------------------------------------------------------
backup_env_vars() {
    log_info "Exportando variables de entorno..."

    # Lista de variables a exportar (excluyendo secrets sensibles del backup)
    local env_vars=(
        "DATABASE_URL"
        "JWT_SECRET_KEY"
        "OPENAI_API_KEY"
        "ANTHROPIC_API_KEY"
        "AI_PROVIDER"
        "RAILWAY_ENVIRONMENT"
        "RAILWAY_SERVICE_NAME"
    )

    # Crear archivo temporal con las variables
    local temp_env="/tmp/env_backup_${TIMESTAMP}.txt"

    echo "# Railway Environment Backup" > "$temp_env"
    echo "# Timestamp: $TIMESTAMP" >> "$temp_env"
    echo "# ==========================" >> "$temp_env"

    for var in "${env_vars[@]}"; do
        if [[ -n "${!var:-}" ]]; then
            echo "${var}=${!var}" >> "$temp_env"
        fi
    done

    # Encriptar con OpenSSL usando AES-256-CBC
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -in "$temp_env" \
        -out "$ENV_BACKUP_FILE" \
        -pass pass:"$BACKUP_ENCRYPTION_KEY"

    # Limpiar archivo temporal
    rm -f "$temp_env"

    if [[ -f "$ENV_BACKUP_FILE" ]]; then
        log_info "Backup de variables de entorno completado: $ENV_BACKUP_FILE"
    else
        log_error "Error al crear backup de variables de entorno"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Rotación de backups antiguos (>14 días)
# -----------------------------------------------------------------------------
rotate_backups() {
    log_info "Ejecutando rotación de backups (eliminando >$BACKUP_RETENTION_DAYS días)..."

    local deleted_count=0

    # Encontrar y eliminar archivos más antiguos que BACKUP_RETENTION_DAYS
    while IFS= read -r -d '' file; do
        log_info "Eliminando backup antiguo: $file"
        rm -f "$file"
        ((deleted_count++))
    done < <(find "$BACKUP_DIR" -type f \( -name "db_*.sql.gz" -o -name "env_*.enc" \) -mtime +$BACKUP_RETENTION_DAYS -print0 2>/dev/null)

    if [[ $deleted_count -gt 0 ]]; then
        log_info "Se eliminaron $deleted_count backups antiguos"
    else
        log_info "No hay backups antiguos para eliminar"
    fi
}

# -----------------------------------------------------------------------------
# Commit y push a GitHub
# -----------------------------------------------------------------------------
push_to_github() {
    log_info "Subiendo backups a GitHub..."

    # Configurar git si es necesario
    git config user.email "${GIT_USER_EMAIL:-backup-bot@railway.app}"
    git config user.name "${GIT_USER_NAME:-Railway Backup Bot}"

    # Añadir archivos de backup
    git add "$BACKUP_DIR"

    # Verificar si hay cambios para commit
    if git diff --staged --quiet; then
        log_warn "No hay cambios nuevos para commit"
        return 0
    fi

    # Crear commit con mensaje descriptivo
    git commit -m "backup: PostgreSQL dump ${TIMESTAMP}

- Database backup: db_${TIMESTAMP}.sql.gz
- Environment backup: env_${TIMESTAMP}.enc
- Retention: ${BACKUP_RETENTION_DAYS} days

[automated backup]"

    # Push a la rama actual
    git push origin HEAD

    log_info "Backup subido a GitHub exitosamente"
}

# -----------------------------------------------------------------------------
# Generar reporte de backup
# -----------------------------------------------------------------------------
generate_report() {
    log_info "Generando reporte de backup..."

    local report_file="${BACKUP_DIR}/backup_report.json"
    local db_size=$(stat -f%z "$DB_BACKUP_FILE" 2>/dev/null || stat -c%s "$DB_BACKUP_FILE" 2>/dev/null || echo "0")
    local env_size=$(stat -f%z "$ENV_BACKUP_FILE" 2>/dev/null || stat -c%s "$ENV_BACKUP_FILE" 2>/dev/null || echo "0")
    local total_backups=$(find "$BACKUP_DIR" -name "db_*.sql.gz" | wc -l | tr -d ' ')

    cat > "$report_file" << EOF
{
    "last_backup": {
        "timestamp": "$TIMESTAMP",
        "database_file": "$DB_BACKUP_FILE",
        "database_size_bytes": $db_size,
        "env_file": "$ENV_BACKUP_FILE",
        "env_size_bytes": $env_size
    },
    "retention_days": $BACKUP_RETENTION_DAYS,
    "total_backups": $total_backups,
    "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

    log_info "Reporte generado: $report_file"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    log_info "=========================================="
    log_info "Iniciando backup automático de Railway"
    log_info "Timestamp: $TIMESTAMP"
    log_info "=========================================="

    validate_env
    setup_backup_dir
    backup_database
    backup_env_vars
    rotate_backups
    generate_report

    # Solo hacer push si estamos en CI/CD o si se especifica
    if [[ "${GITHUB_ACTIONS:-false}" == "true" ]] || [[ "${PUSH_TO_GITHUB:-false}" == "true" ]]; then
        push_to_github
    else
        log_info "Saltando push a GitHub (ejecutar con PUSH_TO_GITHUB=true para habilitar)"
    fi

    log_info "=========================================="
    log_info "Backup completado exitosamente"
    log_info "=========================================="
}

main "$@"
