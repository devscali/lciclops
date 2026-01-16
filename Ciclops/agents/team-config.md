---
name: little-caesars-reports-team
description: Configuración del equipo de agentes para el sistema de reportes financieros de Little Caesars
version: 1.0.0
---

# Equipo Little Caesars Reports 🍕

## Resumen del Equipo

| Agente | Rol | Especialidad | Archivo |
|--------|-----|--------------|---------|
| **Livia** | Coordinadora | Orquestación y comunicación | `livia-coordinator.md` |
| **Julia** | Data Scientist | Análisis de datos y PDFs | `julia-data-scientist.md` |
| **Elena** | UI/UX Designer | Diseño de interfaces | `elena-ui-ux-designer.md` |
| **Aurelia** | Backend Architect | Arquitectura y APIs | `aurelia-backend-architect.md` |

## Diagrama de Comunicación

```
                         USUARIO
                            │
                            ▼
                    ┌───────────────┐
                    │     LIVIA     │
                    │  Coordinadora │
                    └───────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │    JULIA    │   │    ELENA    │   │   AURELIA   │
   │    Data     │◄─►│    UI/UX    │◄─►│   Backend   │
   │  Scientist  │   │   Designer  │   │  Architect  │
   └─────────────┘   └─────────────┘   └─────────────┘
```

## Flujos de Trabajo

### Flujo 1: Procesar Documento
```
1. Usuario → Livia: "Sube PDF"
2. Livia → Julia: "Procesa esto"
3. Julia: OCR + Extracción + Claude API
4. Julia → Livia: Datos estructurados
5. Livia → Elena: "Visualiza estos datos"
6. Elena: Genera dashboard/reporte
7. Livia → Usuario: Presenta resultado
```

### Flujo 2: Generar Reporte
```
1. Usuario → Livia: "Dame el P&L de enero"
2. Livia → Julia: "Consulta datos de enero"
3. Julia: Query Firestore + Análisis
4. Julia → Elena: "Genera el reporte"
5. Elena: Diseña reporte visual
6. Livia → Usuario: Entrega reporte
```

### Flujo 3: Nuevo Feature
```
1. Usuario → Livia: "Necesito una nueva pantalla"
2. Livia → Elena: "Diseña la pantalla"
3. Elena: Wireframe + Especificaciones
4. Elena → Aurelia: "Define el API para esto"
5. Aurelia: Diseña endpoints + esquemas
6. Livia → Usuario: Plan de implementación
```

## Reglas del Equipo

### Comunicación
- Todas hablan español mexicano
- Cada una tiene personalidad distintiva
- Livia es el único punto de contacto con el usuario
- Las agentes pueden colaborar entre ellas

### Delegación (Livia decide)
- **Datos/Números/PDFs** → Julia
- **Diseño/UI/Visuales** → Elena
- **Técnico/APIs/Backend** → Aurelia
- **General/Simple** → Livia directa

### Calidad
- Julia valida datos antes de reportar
- Elena asegura accesibilidad WCAG 2.1 AA
- Aurelia revisa seguridad y performance
- Livia confirma que el usuario está satisfecho

## Configuración Técnica

### Variables de Entorno Requeridas
```bash
# Firebase
FIREBASE_PROJECT_ID=little-caesars-reports
FIREBASE_API_KEY=xxx
FIREBASE_AUTH_DOMAIN=xxx.firebaseapp.com

# Claude API
ANTHROPIC_API_KEY=xxx

# Backend
API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000

# Storage
GCS_BUCKET=little-caesars-documents
```

### Estructura de Carpetas del Proyecto
```
little-caesars-reports/
├── frontend/                 # React + TailwindCSS
│   ├── src/
│   │   ├── components/       # Componentes UI (Elena)
│   │   ├── pages/           # Páginas
│   │   ├── hooks/           # Custom hooks
│   │   ├── services/        # API calls
│   │   └── styles/          # Design tokens (Elena)
│   └── package.json
│
├── backend/                  # Python + FastAPI (Aurelia)
│   ├── app/
│   │   ├── routers/         # Endpoints
│   │   ├── services/        # Lógica de negocio (Julia)
│   │   ├── models/          # Pydantic models
│   │   └── utils/           # Helpers
│   ├── requirements.txt
│   └── main.py
│
├── agents/                   # Definiciones de agentes
│   ├── julia-data-scientist.md
│   ├── elena-ui-ux-designer.md
│   ├── livia-coordinator.md
│   ├── aurelia-backend-architect.md
│   └── team-config.md
│
├── docs/                     # Documentación
│   ├── api.md
│   ├── database.md
│   └── design-system.md
│
└── firebase/                 # Configuración Firebase
    ├── firestore.rules
    └── storage.rules
```

## Métricas del Equipo

### KPIs por Agente

| Agente | Métrica Principal | Target |
|--------|-------------------|--------|
| Julia | Precisión de extracción | >95% |
| Elena | Satisfacción de UI | >4.5/5 |
| Aurelia | Uptime del API | >99.9% |
| Livia | Tiempo de respuesta | <3s |

## Escalabilidad

### Fase 1 (MVP)
- 1-10 usuarios
- 1 franquicia
- Reportes básicos

### Fase 2 (Growth)
- 10-50 usuarios
- Múltiples franquicias
- Reportes avanzados
- Comparativos

### Fase 3 (Scale)
- 50+ usuarios
- Multi-tenant
- API pública
- Integraciones POS

---

*Equipo creado para Little Caesars Reports - Sistema de reportes financieros automatizados*
