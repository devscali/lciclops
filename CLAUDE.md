# CLAUDE.md - Base de Conocimiento del Proyecto

## Advertencias Importantes

### SIEMPRE ANTES DE CAMBIOS DESTRUCTIVOS
Antes de hacer cualquier operación que pueda afectar datos en producción:
- Migraciones de base de datos
- Cambios en modelos/schemas
- DELETE, UPDATE masivos
- Cambios en estructura de tablas
- Deploy de cambios grandes

**ADVERTIR AL USUARIO:** "¿Quieres que corra un backup antes de entrar a los vergazos?"

### Sistema de Backups
- Backups automáticos diarios a las 3:00 AM UTC (9:00 PM México)
- Ubicación: `backups/` en el repo
- Formato: `db_YYYY-MM-DD_HH-MM-SS.sql.gz`
- Retención: 14 días
- Restaurar: `./scripts/restore.sh --timestamp YYYY-MM-DD_HH-MM-SS`
- Backup manual: Ejecutar workflow desde GitHub Actions

## Stack del Proyecto

- **Backend:** FastAPI + Python
- **Base de datos:** PostgreSQL (Railway)
- **AI:** Anthropic Claude / OpenAI (fallback)
- **Deploy:** Railway
- **Dominio:** lc.calidevs.com

## Archivos Clave

- `app/main_postgres.py` - Entry point de la API
- `app/database.py` - Conexión a PostgreSQL
- `app/db_models.py` - Modelos SQLAlchemy
- `railway.json` - Config de deploy

## Comandos Útiles

```bash
# Ver backups disponibles
./scripts/restore.sh --list

# Restaurar backup específico
./scripts/restore.sh --timestamp 2026-01-25_01-05-02

# Backup manual inmediato
gh workflow run backup.yml --repo devscali/lciclops

# Variables de Railway
railway variables
```
