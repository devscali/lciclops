# Little Caesars Reports

Sistema de reportes financieros automatizados para franquicias Little Caesars.

## Equipo de Desarrollo

| Agente | Rol | Especialidad |
|--------|-----|--------------|
| **Livia** | Coordinadora | Orquestacion y comunicacion |
| **Julia** | Data Scientist | Analisis de datos y PDFs |
| **Elena** | UI/UX Designer | Diseno de interfaces |
| **Aurelia** | Backend Architect | Arquitectura y APIs |

## Stack Tecnologico

### Backend
- Python 3.11+
- FastAPI
- Firebase Admin SDK
- Claude API (Anthropic)
- pytesseract + pdfplumber (OCR)

### Frontend
- Next.js 14
- React 18
- TailwindCSS
- Recharts
- Firebase Auth

### Infraestructura
- Firebase (Auth, Firestore, Storage)
- Cloud Functions (opcional)

## Estructura del Proyecto

```
little-caesars-reports/
├── frontend/                 # React + TailwindCSS
│   ├── src/
│   │   ├── components/       # Componentes UI
│   │   ├── pages/            # Paginas
│   │   ├── services/         # API y Firebase
│   │   └── styles/           # Estilos globales
│   └── package.json
│
├── backend/                  # Python + FastAPI
│   ├── app/
│   │   ├── routers/          # Endpoints
│   │   ├── services/         # Logica de negocio
│   │   ├── models/           # Pydantic models
│   │   └── config.py         # Configuracion
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
└── firebase/                 # Configuracion Firebase
    └── firestore.rules
```

## Instalacion

### Prerequisitos
- Python 3.11+
- Node.js 18+
- Tesseract OCR
- Cuenta de Firebase
- API Key de Anthropic (Claude)

### Backend

```bash
cd backend

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar servidor
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend

# Instalar dependencias
npm install

# Copiar variables de entorno
cp .env.example .env.local
# Editar .env.local con tus credenciales

# Ejecutar servidor de desarrollo
npm run dev
```

## Configuracion de Firebase

1. Crear proyecto en [Firebase Console](https://console.firebase.google.com)
2. Habilitar Authentication (Email/Password y Google)
3. Crear base de datos Firestore
4. Crear bucket en Cloud Storage
5. Descargar credenciales del Service Account
6. Guardar como `firebase-credentials.json` en `/backend`

## API Endpoints

### Auth
- `POST /api/auth/setup-profile` - Configurar perfil
- `GET /api/auth/me` - Obtener perfil actual
- `PUT /api/auth/profile` - Actualizar perfil

### Documents
- `POST /api/documents/upload` - Subir documento
- `GET /api/documents` - Listar documentos
- `GET /api/documents/:id` - Obtener documento
- `DELETE /api/documents/:id` - Eliminar documento
- `POST /api/documents/:id/reprocess` - Reprocesar documento

### Reports
- `GET /api/reports/dashboard` - Datos del dashboard
- `GET /api/reports/pnl` - Estado de resultados
- `GET /api/reports/sales` - Reporte de ventas
- `GET /api/reports/insights` - Insights con IA
- `POST /api/reports/export` - Exportar a PDF/Excel

## Uso

1. Registrate o inicia sesion
2. Sube un documento (PDF, imagen)
3. Julia lo procesara automaticamente
4. Ve los datos extraidos y las metricas
5. Genera reportes y exportalos

## Licencia

Proyecto privado - Little Caesars
