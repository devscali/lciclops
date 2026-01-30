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

- `app/main_postgres.py` - Entry point de la API (incluye SmartDocumentProcessor)
- `app/database.py` - Conexión a PostgreSQL
- `app/db_models.py` - Modelos SQLAlchemy
- `index.html` - Dashboard frontend con 19 gráficas
- `railway.json` - Config de deploy

## Estado Actual del Sistema (Enero 2026)

### Datos en Producción
- **3 documentos procesados:** P11, P12, P13 (Estado de Resultados)
- **17 tiendas** con datos financieros
- **51 registros** en `monthly_summaries` (17 tiendas × 3 períodos)
- **Dashboard funcional** con datos reales

### Tiendas Activas
```
GUAYMITAS, CABOS, MI PLAZA, VISTA, CAMINO, MANEADERO, ´5 FEB,
CONSTITUCION, FORJADORES, DELANTE, OLIVARES, SANTA FE, PASEO,
SOL, TAMARAL, SAN MARINO, CENTRO
```

### Períodos Fiscales Little Caesars
- 13 períodos por año (P1-P13)
- Cada período = 4 semanas
- Semana empieza Martes, termina Lunes
- P13 = Diciembre (semanas 49-52)

## SmartDocumentProcessor (AI-Powered)

Sistema inteligente que procesa CUALQUIER documento automáticamente.

### Qué hace:
1. **Detecta tipo de documento** - estado_resultados, estado_cuenta, nomina, inventario
2. **Extrae período del CONTENIDO** - no solo del nombre de archivo
3. **Identifica tiendas** - automáticamente de los datos
4. **Mapea conceptos** - NOMINAS, ALQUILER, CFE → categorías estándar
5. **Guarda en BD** - `monthly_summaries` listo para gráficas

### Conceptos que entiende:
```
ingresos     → INGRESOS, VENTAS, REVENUE, TOTAL VENTAS
costo_ventas → AXION, PEPSI, VERDURAS, AGUA PURIFICADA, COMPRAS
nomina       → NOMINAS, AGUINALDOS, IMSS, BONOS, VACACIONES
renta        → ALQUILER, MTTO ALQUILER, ARRENDAMIENTO
servicios    → CFE, AGUA, GAS, TELMEX, INTERNET
utilidad     → UTILIDAD BRUTA, UTILIDAD NETA, GANANCIA
```

### Endpoints de Procesamiento:
```bash
# Procesar 1 documento con AI
POST /process/smart/{doc_id}

# Procesar todos los documentos en batch
POST /process/smart-batch

# Preview sin guardar (para validar)
GET /process/smart-preview/{doc_id}

# Confirmación con smart processing (default)
POST /upload/confirm?smart_process=true
```

## Dashboard y Gráficas

### 19 Gráficas Disponibles:
| Gráfica | Descripción | Datos |
|---------|-------------|-------|
| revenueChart | Ingresos/Utilidad por tienda | ✅ Real |
| expenseChart | Desglose de gastos | ✅ Real |
| trendChart | Tendencia P11→P13 | ✅ Real |
| rankingChart | Ranking por margen | ✅ Real |
| correlationChart | Ventas vs Gastos | ✅ Real |
| expenseDistChart | Distribución % | ✅ Real |
| compareChart | Actual vs Anterior | ✅ Real |
| topCategoriesChart | Top gastos | ✅ Real |
| radarChart | Multidimensional | ✅ Real |
| efficiencyChart | Gauge eficiencia | ✅ Real |
| marginCompareChart | Margen bruto/neto | ✅ Real |
| laborRatioChart | Ratio nómina | ✅ Real |
| fixedCostsChart | Costos fijos | ✅ Real |
| costStructureChart | Estructura costos | ✅ Real |
| marginEvolutionChart | Evolución márgenes | ✅ Real |
| waterfallChart | Cascada P&L | ✅ Real |
| scatterMarginChart | Dispersión margen | ✅ Real |
| rentRatioChart | Ratio renta | ✅ Real |
| momVariationChart | Variación MoM | Pendiente |

### Modales
Todas las gráficas tienen modal con datos reales del API (no demo data).

## Pendientes (Febrero 2026)

1. **PDFs Estados de Cuenta** - El SmartProcessor ya está preparado
2. **Pedir a clientas formato de documentos** - Para mejor entrenamiento
3. **momVariationChart** - Necesita cálculo de `sales_vs_previous`

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

# Verificar sintaxis Python
python3 -m py_compile app/main_postgres.py

# Ver logs de Railway
railway logs
```

## Flujo de Datos

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Cliente   │────▶│  SmartProcessor  │────▶│ monthly_        │────▶│  Dashboard   │
│  sube Excel │     │  (Claude/GPT-4)  │     │ summaries (BD)  │     │  (19 charts) │
│  o PDF      │     │                  │     │                 │     │              │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │ Detecta:         │
                    │ • Tipo documento │
                    │ • Período fiscal │
                    │ • Tiendas        │
                    │ • Conceptos      │
                    └──────────────────┘
```
