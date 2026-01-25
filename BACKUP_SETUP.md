# Configuración de Backup Automático - Railway PostgreSQL

## Resumen

Este sistema realiza backups automáticos diarios que incluyen:
- **PostgreSQL dump comprimido** (gzip)
- **Variables de entorno encriptadas** (AES-256)
- **Rotación automática** (elimina backups >14 días)
- **Timestamps completos** para restauración a hora específica

## Configuración de GitHub Secrets

Debes configurar los siguientes secrets en tu repositorio de GitHub:

### 1. Ir a Settings → Secrets and variables → Actions

### 2. Crear los siguientes secrets:

| Secret | Descripción | Cómo obtenerlo |
|--------|-------------|----------------|
| `DATABASE_URL` | URL de conexión PostgreSQL | Railway Dashboard → Variables |
| `JWT_SECRET_KEY` | Clave JWT de tu aplicación | Railway Dashboard → Variables |
| `OPENAI_API_KEY` | API key de OpenAI (opcional) | Railway Dashboard → Variables |
| `ANTHROPIC_API_KEY` | API key de Anthropic | Railway Dashboard → Variables |
| `BACKUP_ENCRYPTION_KEY` | Clave para encriptar variables | Generar una nueva (ver abajo) |

### 3. Generar BACKUP_ENCRYPTION_KEY

Ejecuta este comando para generar una clave segura:

```bash
openssl rand -base64 32
```

**Guarda esta clave en un lugar seguro** - la necesitarás para restaurar las variables de entorno.

## Estructura de Archivos

```
lciclops/
├── .github/
│   └── workflows/
│       └── backup.yml          # GitHub Action (ejecuta diario 3AM UTC)
├── scripts/
│   ├── backup.sh               # Script de backup manual
│   └── restore.sh              # Script de restauración
├── backups/
│   ├── db_YYYY-MM-DD_HH-MM-SS.sql.gz    # Dumps de PostgreSQL
│   ├── env_YYYY-MM-DD_HH-MM-SS.enc      # Variables encriptadas
│   └── backup_report.json               # Reporte del último backup
└── BACKUP_SETUP.md             # Esta documentación
```

## Uso

### Ver backups disponibles

```bash
./scripts/restore.sh --list
```

### Restaurar a timestamp específico

```bash
# Configurar variables
export DATABASE_URL="postgresql://..."
export BACKUP_ENCRYPTION_KEY="tu-clave-de-encriptacion"

# Restaurar
./scripts/restore.sh --timestamp 2024-01-15_03-00-00
```

### Restaurar solo base de datos

```bash
./scripts/restore.sh --timestamp 2024-01-15_03-00-00 --database-only
```

### Restaurar solo variables de entorno

```bash
./scripts/restore.sh --timestamp 2024-01-15_03-00-00 --env-only
```

### Ejecutar backup manual

```bash
export DATABASE_URL="postgresql://..."
export BACKUP_ENCRYPTION_KEY="tu-clave"
export PUSH_TO_GITHUB=true  # Opcional: hacer push automático

./scripts/backup.sh
```

## Programación

El backup se ejecuta automáticamente:
- **Frecuencia:** Diario
- **Hora:** 3:00 AM UTC (9:00 PM hora México)
- **Retención:** 14 días

### Ejecutar backup manual desde GitHub

1. Ir a **Actions** → **Railway Database Backup**
2. Click en **Run workflow**
3. Seleccionar rama y ejecutar

## Formato de Nombres

Los backups usan timestamp completo para facilitar restauración a hora específica:

```
db_YYYY-MM-DD_HH-MM-SS.sql.gz
env_YYYY-MM-DD_HH-MM-SS.enc
```

Ejemplo:
```
db_2024-01-15_03-00-00.sql.gz  → Backup del 15 de enero 2024 a las 3:00:00 AM
```

## Seguridad

- **Variables de entorno:** Encriptadas con AES-256-CBC, PBKDF2 con 100,000 iteraciones
- **Base de datos:** Solo dump SQL comprimido (sin encriptar - los datos sensibles ya están hasheados en BD)
- **Clave de encriptación:** Almacenada solo en GitHub Secrets

## Troubleshooting

### Error: "No se pudo parsear DATABASE_URL"

Verifica que el formato sea:
```
postgresql://usuario:contraseña@host:puerto/basededatos
```

### Error al desencriptar variables

Verifica que `BACKUP_ENCRYPTION_KEY` sea exactamente la misma usada para encriptar.

### El workflow falla con permisos

Asegúrate que el workflow tenga permisos de escritura:
- Settings → Actions → General → Workflow permissions → Read and write permissions

## Verificar que funciona

Después de configurar:

1. Ejecutar manualmente el workflow desde GitHub Actions
2. Verificar que se creen archivos en `backups/`
3. Probar restauración en un entorno de prueba
