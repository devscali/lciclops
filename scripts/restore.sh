#!/bin/bash
# =============================================================================
# Railway PostgreSQL Restore Script
# =============================================================================
# Restaura backups de PostgreSQL y variables de entorno
# Soporta restauración a timestamp específico
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------
BACKUP_DIR="backups"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_prompt() {
    echo -e "${BLUE}[INPUT]${NC} $1"
}

# -----------------------------------------------------------------------------
# Mostrar ayuda
# -----------------------------------------------------------------------------
show_help() {
    cat << EOF
Railway PostgreSQL Restore Script

USO:
    ./restore.sh [opciones]

OPCIONES:
    -t, --timestamp TIMESTAMP   Restaurar backup específico (formato: YYYY-MM-DD_HH-MM-SS)
    -l, --list                  Listar todos los backups disponibles
    -d, --database-only         Solo restaurar base de datos (no variables de entorno)
    -e, --env-only              Solo restaurar variables de entorno (no base de datos)
    -f, --force                 No pedir confirmación
    -h, --help                  Mostrar esta ayuda

EJEMPLOS:
    # Listar backups disponibles
    ./restore.sh --list

    # Restaurar backup específico
    ./restore.sh --timestamp 2024-01-15_03-00-00

    # Restaurar solo la base de datos del backup más reciente
    ./restore.sh --database-only

    # Restaurar sin confirmación
    ./restore.sh --timestamp 2024-01-15_03-00-00 --force

VARIABLES DE ENTORNO REQUERIDAS:
    DATABASE_URL              URL de conexión a PostgreSQL
    BACKUP_ENCRYPTION_KEY     Clave para desencriptar variables de entorno

EOF
}

# -----------------------------------------------------------------------------
# Listar backups disponibles
# -----------------------------------------------------------------------------
list_backups() {
    log_info "Backups disponibles en $BACKUP_DIR:"
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  TIMESTAMP            │  DB SIZE    │  ENV  │  FECHA ARCHIVO   ║"
    echo "╠════════════════════════════════════════════════════════════════╣"

    local found=0

    # Buscar archivos de backup de DB ordenados por fecha (más reciente primero)
    for db_file in $(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null); do
        found=1
        local filename=$(basename "$db_file")
        # Extraer timestamp del nombre: db_YYYY-MM-DD_HH-MM-SS.sql.gz
        local timestamp="${filename#db_}"
        timestamp="${timestamp%.sql.gz}"

        local db_size=$(du -h "$db_file" | cut -f1)
        local env_file="${BACKUP_DIR}/env_${timestamp}.enc"
        local has_env="NO"
        [[ -f "$env_file" ]] && has_env="SI"

        local file_date=$(date -r "$db_file" "+%Y-%m-%d %H:%M" 2>/dev/null || stat -c %y "$db_file" 2>/dev/null | cut -d' ' -f1,2 | cut -d'.' -f1)

        printf "║  %-19s │  %-9s │  %-3s  │  %-16s ║\n" "$timestamp" "$db_size" "$has_env" "$file_date"
    done

    echo "╚════════════════════════════════════════════════════════════════╝"

    if [[ $found -eq 0 ]]; then
        log_warn "No se encontraron backups en $BACKUP_DIR"
        return 1
    fi

    echo ""
    log_info "Usa --timestamp TIMESTAMP para restaurar un backup específico"
}

# -----------------------------------------------------------------------------
# Obtener el backup más reciente
# -----------------------------------------------------------------------------
get_latest_backup() {
    local latest=$(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)

    if [[ -z "$latest" ]]; then
        log_error "No se encontraron backups"
        exit 1
    fi

    local filename=$(basename "$latest")
    local timestamp="${filename#db_}"
    timestamp="${timestamp%.sql.gz}"

    echo "$timestamp"
}

# -----------------------------------------------------------------------------
# Validar timestamp
# -----------------------------------------------------------------------------
validate_timestamp() {
    local timestamp="$1"
    local db_file="${BACKUP_DIR}/db_${timestamp}.sql.gz"

    if [[ ! -f "$db_file" ]]; then
        log_error "No se encontró backup para timestamp: $timestamp"
        log_info "Usa --list para ver backups disponibles"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Restaurar base de datos
# -----------------------------------------------------------------------------
restore_database() {
    local timestamp="$1"
    local db_file="${BACKUP_DIR}/db_${timestamp}.sql.gz"

    log_info "Restaurando base de datos desde: $db_file"

    # Parsear DATABASE_URL
    if [[ "$DATABASE_URL" =~ ^postgres(ql)?://([^:]+):([^@]+)@([^:]+):([0-9]+)/(.+)$ ]]; then
        DB_USER="${BASH_REMATCH[2]}"
        DB_PASS="${BASH_REMATCH[3]}"
        DB_HOST="${BASH_REMATCH[4]}"
        DB_PORT="${BASH_REMATCH[5]}"
        DB_NAME="${BASH_REMATCH[6]}"
        DB_NAME="${DB_NAME%%\?*}"
    else
        log_error "No se pudo parsear DATABASE_URL"
        exit 1
    fi

    log_warn "ADVERTENCIA: Esto sobrescribirá todos los datos en la base de datos"
    log_info "Base de datos destino: $DB_HOST:$DB_PORT/$DB_NAME"

    # Descomprimir y restaurar
    gunzip -c "$db_file" | PGPASSWORD="$DB_PASS" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --quiet \
        --set ON_ERROR_STOP=on

    if [[ $? -eq 0 ]]; then
        log_info "Base de datos restaurada exitosamente"
    else
        log_error "Error al restaurar base de datos"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Restaurar variables de entorno
# -----------------------------------------------------------------------------
restore_env_vars() {
    local timestamp="$1"
    local env_file="${BACKUP_DIR}/env_${timestamp}.enc"
    local output_file="${2:-.env.restored}"

    if [[ ! -f "$env_file" ]]; then
        log_warn "No se encontró archivo de variables de entorno: $env_file"
        return 1
    fi

    log_info "Desencriptando variables de entorno desde: $env_file"

    # Desencriptar
    openssl enc -aes-256-cbc -d -pbkdf2 -iter 100000 \
        -in "$env_file" \
        -out "$output_file" \
        -pass pass:"$BACKUP_ENCRYPTION_KEY"

    if [[ $? -eq 0 ]] && [[ -f "$output_file" ]]; then
        log_info "Variables de entorno restauradas en: $output_file"
        echo ""
        echo "Contenido (sensible - no compartir):"
        echo "======================================"
        cat "$output_file"
        echo "======================================"
        echo ""
        log_warn "IMPORTANTE: Copia estas variables a tu configuración de Railway"
    else
        log_error "Error al desencriptar variables de entorno"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Pedir confirmación
# -----------------------------------------------------------------------------
confirm_restore() {
    local timestamp="$1"
    local restore_type="$2"

    echo ""
    log_warn "═══════════════════════════════════════════════════════════════"
    log_warn "                    CONFIRMACIÓN DE RESTAURACIÓN"
    log_warn "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  Timestamp:  $timestamp"
    echo "  Tipo:       $restore_type"
    echo ""
    log_warn "Esta acción puede sobrescribir datos existentes."
    echo ""

    read -p "¿Continuar con la restauración? (escribe 'SI' para confirmar): " confirm

    if [[ "$confirm" != "SI" ]]; then
        log_info "Restauración cancelada"
        exit 0
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    local timestamp=""
    local list_only=false
    local db_only=false
    local env_only=false
    local force=false

    # Parsear argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--timestamp)
                timestamp="$2"
                shift 2
                ;;
            -l|--list)
                list_only=true
                shift
                ;;
            -d|--database-only)
                db_only=true
                shift
                ;;
            -e|--env-only)
                env_only=true
                shift
                ;;
            -f|--force)
                force=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Opción desconocida: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Verificar directorio de backups
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Directorio de backups no encontrado: $BACKUP_DIR"
        exit 1
    fi

    # Solo listar
    if [[ "$list_only" == true ]]; then
        list_backups
        exit 0
    fi

    # Validar variables requeridas
    if [[ -z "${DATABASE_URL:-}" ]] && [[ "$env_only" == false ]]; then
        log_error "DATABASE_URL no está configurada"
        exit 1
    fi

    if [[ -z "${BACKUP_ENCRYPTION_KEY:-}" ]] && [[ "$db_only" == false ]]; then
        log_error "BACKUP_ENCRYPTION_KEY no está configurada"
        exit 1
    fi

    # Usar backup más reciente si no se especifica timestamp
    if [[ -z "$timestamp" ]]; then
        timestamp=$(get_latest_backup)
        log_info "Usando backup más reciente: $timestamp"
    fi

    validate_timestamp "$timestamp"

    # Determinar tipo de restauración
    local restore_type="Completa (DB + ENV)"
    [[ "$db_only" == true ]] && restore_type="Solo base de datos"
    [[ "$env_only" == true ]] && restore_type="Solo variables de entorno"

    # Confirmación
    if [[ "$force" == false ]]; then
        confirm_restore "$timestamp" "$restore_type"
    fi

    log_info "=========================================="
    log_info "Iniciando restauración"
    log_info "Timestamp: $timestamp"
    log_info "=========================================="

    # Restaurar DB
    if [[ "$env_only" == false ]]; then
        restore_database "$timestamp"
    fi

    # Restaurar ENV
    if [[ "$db_only" == false ]]; then
        restore_env_vars "$timestamp"
    fi

    log_info "=========================================="
    log_info "Restauración completada exitosamente"
    log_info "=========================================="
}

main "$@"
