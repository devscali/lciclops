"""
CICLOPS Backend - Producción con PostgreSQL
API para análisis financiero de Little Caesars
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, Request, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from openai import OpenAI
import pandas as pd
import numpy as np
import json
import os
import math
from io import BytesIO
from dotenv import load_dotenv
from typing import Optional, List
import traceback
import pdfplumber
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import engine, get_db, Base
from . import db_models as models
from . import schemas

# Cargar variables de entorno
load_dotenv()

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CICLOPS API",
    description="API para análisis financiero de Little Caesars con Julia AI",
    version="2.0.0"
)


# Middleware para forzar HTTPS (Railway usa proxy)
class ForceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Railway pone el protocolo original en X-Forwarded-Proto
        forwarded_proto = request.headers.get("x-forwarded-proto", "https")
        if forwarded_proto == "http":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(url), status_code=301)
        return await call_next(request)


# Agregar middleware (orden importa: HTTPS primero)
app.add_middleware(ForceHTTPSMiddleware)

# CORS - Restringido a orígenes permitidos
ALLOWED_ORIGINS = [
    "https://lc.calidevs.com",
    "https://lciclops-production.up.railway.app",
    "https://lciclops.up.railway.app",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ============================================
# AUTENTICACIÓN CON JWT
# ============================================

# Configuración JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tu-secret-key-cambiar-en-produccion-123")
ALGORITHM = "HS256"
print(f"🔐 JWT Secret Key configurada: {SECRET_KEY[:10]}...{SECRET_KEY[-5:]}")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 días

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt tiene límite de 72 bytes
    return pwd_context.verify(plain_password[:72], hashed_password)


def get_password_hash(password: str) -> str:
    # bcrypt tiene límite de 72 bytes
    return pwd_context.hash(password[:72])


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    """Verifica el token JWT y retorna los datos del usuario."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorización requerido",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    return {
        "id": user.id,
        "uid": str(user.id),  # Compatibilidad con código existente
        "email": user.email,
        "name": user.name,
        "role": user.role
    }


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """Verifica el token si existe, pero no falla si no hay token."""
    if not credentials:
        return None

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            return None

        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.is_active:
            return None

        return {
            "id": user.id,
            "uid": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
    except JWTError:
        return None


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Verifica que el usuario sea administrador"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador"
        )
    return current_user

# Clientes de AI
openai_client = None
anthropic_client = None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # Default to Anthropic/Claude

# Inicializar OpenAI si hay key
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI API configurada")
else:
    print("⚠️ OPENAI_API_KEY no encontrada")

# Inicializar Anthropic si hay key
try:
    import anthropic
    if ANTHROPIC_API_KEY:
        anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        print("✅ Anthropic API configurada")
    else:
        print("⚠️ ANTHROPIC_API_KEY no encontrada")
except ImportError:
    print("⚠️ anthropic module not installed")


# ============================================
# HELPER DE IA CON FALLBACK
# ============================================

def call_ai_with_fallback(messages: list, max_tokens: int = 1500, temperature: float = 0.7) -> dict:
    """
    Llama a la IA con fallback automático entre proveedores.
    Intenta primero con el proveedor configurado, luego con el otro.
    Retorna: {"response": str, "tokens_used": int, "provider": str}
    """
    errors = []

    # Determinar orden de proveedores
    if AI_PROVIDER == "anthropic" and anthropic_client:
        providers = [("anthropic", anthropic_client), ("openai", openai_client)]
    else:
        providers = [("openai", openai_client), ("anthropic", anthropic_client)]

    for provider_name, client in providers:
        if not client:
            continue

        try:
            if provider_name == "openai":
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return {
                    "response": response.choices[0].message.content,
                    "tokens_used": response.usage.total_tokens,
                    "provider": "openai"
                }
            else:  # anthropic
                # Convertir mensajes de OpenAI format a Anthropic format
                system_msg = ""
                anthropic_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_msg = msg["content"]
                    else:
                        anthropic_messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })

                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    system=system_msg,
                    messages=anthropic_messages
                )
                return {
                    "response": response.content[0].text,
                    "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                    "provider": "anthropic"
                }

        except Exception as e:
            error_msg = f"[IA ERROR] {provider_name} falló: {str(e)}"
            print(f"⚠️ {error_msg}")
            errors.append(error_msg)
            continue

    # Si llegamos aquí, ambos fallaron
    error_detail = " | ".join(errors) if errors else "No hay proveedores de IA configurados"
    print(f"❌ [IA CRÍTICO] Todos los proveedores fallaron: {error_detail}")
    raise HTTPException(
        status_code=503,
        detail=f"Servicio de IA no disponible. Por favor intenta más tarde. ({error_detail})"
    )


# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register", response_model=schemas.Token)
async def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """Registra un nuevo usuario"""
    # Verificar si el email ya existe
    existing = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # Crear usuario
    user = models.User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        name=user_data.name,
        role="user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generar token
    token = create_access_token(data={"sub": user.id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }


@app.post("/auth/login", response_model=schemas.Token)
async def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    """Inicia sesión y retorna token JWT"""
    user = db.query(models.User).filter(models.User.email == user_data.email).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario desactivado")

    token = create_access_token(data={"sub": user.id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }


@app.get("/auth/me", response_model=schemas.UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna el usuario actual"""
    user = db.query(models.User).filter(models.User.id == current_user["id"]).first()
    return user


@app.post("/auth/setup-admin")
async def setup_admin(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Crea el primer usuario admin. Solo funciona si no hay usuarios.
    Usar una vez para setup inicial.
    """
    try:
        # Forzar creación de tabla si no existe
        models.User.__table__.create(bind=engine, checkfirst=True)

        # Solo permitir si no hay usuarios
        user_count = db.query(models.User).count()
        if user_count > 0:
            raise HTTPException(status_code=400, detail="Ya existen usuarios. Use /auth/register")

        # Crear admin
        user = models.User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            name=user_data.name or "Admin",
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token(data={"sub": user.id})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creando admin: {str(e)}")


# ============================================
# ENDPOINTS BÁSICOS
# ============================================

@app.get("/api")
async def api_root():
    return {
        "message": "🍕 CICLOPS API - PostgreSQL",
        "status": "running",
        "openai_enabled": openai_client is not None,
        "database": "postgresql"
    }


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    doc_count = db.query(models.Document).count()
    # Verificar usuarios
    try:
        user_count = db.query(models.User).count()
    except Exception as e:
        user_count = f"ERROR: {str(e)}"
    return {
        "status": "healthy",
        "database": "connected",
        "users_count": user_count,
        "openai": "connected" if openai_client else "disabled",
        "anthropic": "connected" if anthropic_client else "disabled",
        "ai_provider": AI_PROVIDER,
        "documents_count": doc_count
    }


# ============================================
# SETTINGS - API Keys Configuration
# ============================================

@app.get("/settings")
async def get_settings():
    """Retorna estado de configuracion (sin exponer keys)"""
    return {
        "openai_key_set": bool(OPENAI_API_KEY),
        "anthropic_key_set": bool(ANTHROPIC_API_KEY),
        "ai_provider": AI_PROVIDER,
        "openai_connected": openai_client is not None,
        "anthropic_connected": anthropic_client is not None
    }


@app.post("/settings")
async def save_settings(
    settings_data: dict,
    current_user: dict = Depends(require_admin)
):
    """
    Guarda configuracion de API keys (requiere restart para aplicar)
    PROTEGIDO: Solo administradores pueden modificar configuración
    """
    global OPENAI_API_KEY, ANTHROPIC_API_KEY, AI_PROVIDER, openai_client, anthropic_client

    messages = []

    # Update OpenAI key if provided
    if settings_data.get("openai_key") and settings_data["openai_key"] != "":
        new_key = settings_data["openai_key"]
        if not new_key.startswith("sk-"):
            return {"success": False, "error": "OpenAI key debe empezar con 'sk-'"}
        try:
            # Test the key
            test_client = OpenAI(api_key=new_key)
            openai_client = test_client
            OPENAI_API_KEY = new_key
            os.environ["OPENAI_API_KEY"] = new_key
            messages.append("OpenAI API key actualizada")
        except Exception as e:
            return {"success": False, "error": f"OpenAI key inválida: {str(e)}"}

    # Update Anthropic key if provided
    if settings_data.get("anthropic_key") and settings_data["anthropic_key"] != "":
        new_key = settings_data["anthropic_key"]
        if not new_key.startswith("sk-ant-"):
            return {"success": False, "error": "Anthropic key debe empezar con 'sk-ant-'"}
        try:
            import anthropic
            test_client = anthropic.Anthropic(api_key=new_key)
            anthropic_client = test_client
            ANTHROPIC_API_KEY = new_key
            os.environ["ANTHROPIC_API_KEY"] = new_key
            messages.append("Anthropic API key actualizada")
        except Exception as e:
            return {"success": False, "error": f"Anthropic key inválida: {str(e)}"}

    # Update AI provider preference
    if settings_data.get("ai_provider"):
        AI_PROVIDER = settings_data["ai_provider"]
        os.environ["AI_PROVIDER"] = AI_PROVIDER
        messages.append(f"Proveedor AI cambiado a: {AI_PROVIDER}")

    return {
        "success": True,
        "messages": messages,
        "status": {
            "openai_connected": openai_client is not None,
            "anthropic_connected": anthropic_client is not None,
            "ai_provider": AI_PROVIDER
        }
    }


# ============================================
# UPLOAD Y DOCUMENTOS
# ============================================

def clean_nan_values(obj):
    """Limpia NaN/Infinity de objetos para JSON válido en PostgreSQL"""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif pd.isna(obj):
        return None
    return obj


def extract_text_from_pdf(content: bytes) -> str:
    """Extrae texto de un PDF usando pdfplumber"""
    text_content = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if row:
                            text_content.append(" | ".join([str(cell) if cell else "" for cell in row]))
            else:
                text = page.extract_text()
                if text:
                    text_content.append(text)
    return "\n".join(text_content)


async def analyze_fields_with_ai(data_preview: list, columns: list, filename: str) -> dict:
    """Usa AI para detectar y mapear campos automáticamente"""
    if not openai_client:
        return {"detected_fields": columns, "mapping": {}, "data_type": "unknown"}

    try:
        # Crear resumen de datos para AI
        sample_data = json.dumps(data_preview[:5], ensure_ascii=False, indent=2)

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Eres un experto en análisis de datos financieros de restaurantes Little Caesars.
Analiza los datos y detecta qué tipo de información contienen.

Responde SOLO con JSON válido con esta estructura:
{
    "data_type": "ventas|gastos|inventario|nomina|estado_resultados|otro",
    "detected_fields": {
        "columna_original": {
            "mapped_to": "nombre_estandarizado",
            "type": "currency|number|text|date|percentage",
            "description": "descripción breve"
        }
    },
    "summary": "descripción de qué contiene este archivo",
    "recommended_category": "categoria sugerida para el vault"
}"""
                },
                {
                    "role": "user",
                    "content": f"""Archivo: {filename}
Columnas detectadas: {columns}

Muestra de datos:
{sample_data}

Analiza y mapea estos campos."""
                }
            ],
            temperature=0.1,
            max_tokens=1000
        )

        result = response.choices[0].message.content
        # Limpiar respuesta de markdown
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        result = result.strip()

        return json.loads(result)
    except Exception as e:
        print(f"Error en análisis AI: {e}")
        return {
            "data_type": "unknown",
            "detected_fields": {col: {"mapped_to": col, "type": "text"} for col in columns},
            "summary": "No se pudo analizar automáticamente",
            "recommended_category": "general"
        }


def detect_period_from_filename(filename: str) -> str:
    """Detecta el periodo/fecha del nombre del archivo"""
    import re

    # Mapeo de periodos a meses
    period_months = {
        'P1': 'Enero', 'P2': 'Febrero', 'P3': 'Marzo', 'P4': 'Abril',
        'P5': 'Mayo', 'P6': 'Junio', 'P7': 'Julio', 'P8': 'Agosto',
        'P9': 'Septiembre', 'P10': 'Octubre', 'P11': 'Noviembre', 'P12': 'Diciembre'
    }

    # Buscar patrón P## (periodo)
    period_match = re.search(r'P(\d{1,2})', filename.upper())
    if period_match:
        period_num = f"P{period_match.group(1)}"
        month = period_months.get(period_num, f"Periodo {period_match.group(1)}")

        # Buscar semanas S## A S##
        weeks_match = re.search(r'S(\d+)\s*A\s*S(\d+)', filename.upper())
        if weeks_match:
            return f"{month} (S{weeks_match.group(1)}-S{weeks_match.group(2)})"
        return month

    # Buscar meses en español
    months_es = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    for month in months_es:
        if month in filename.lower():
            return month.capitalize()

    # Buscar año
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        return year_match.group(0)

    # Default: fecha actual
    from datetime import datetime
    return datetime.now().strftime('%B %Y').capitalize()


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    skip_ai: bool = Query(default=False, description="Skip AI analysis for faster uploads"),
    current_user: dict = Depends(get_current_user)
):
    """
    Sube un archivo y retorna preview para confirmación
    PROTEGIDO: Requiere autenticación
    """
    try:
        filename = file.filename.lower()
        detected_period = detect_period_from_filename(file.filename)
        allowed_extensions = ['.xlsx', '.xls', '.csv', '.pdf']
        if not any(filename.endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail="Solo se permiten archivos Excel, CSV o PDF"
            )

        content = await file.read()
        is_pdf = filename.endswith('.pdf')

        if is_pdf:
            pdf_text = extract_text_from_pdf(content)
            lines = [line.strip() for line in pdf_text.split('\n') if line.strip()]

            # Crear documento en DB
            doc = models.Document(
                filename=file.filename,
                file_type="pdf",
                rows_count=len(lines),
                columns=["contenido"],
                period=detected_period,
                status="pending_confirmation"
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            # Guardar datos raw
            raw_data = models.RawDocumentData(
                document_id=doc.id,
                raw_text=pdf_text,
                preview_data=lines[:20]
            )
            db.add(raw_data)
            db.commit()

            return {
                "success": True,
                "message": f"Archivo '{file.filename}' procesado - pendiente confirmación",
                "document": {
                    "id": doc.id,
                    "filename": doc.filename,
                    "type": "pdf",
                    "rows": len(lines),
                    "columns": ["contenido"],
                    "preview": lines[:10],
                    "status": "pending_confirmation"
                }
            }

        else:
            # Excel o CSV
            if filename.endswith('.csv'):
                # CSV solo tiene una "hoja"
                df = pd.read_csv(BytesIO(content))
                sheets_data = {"Datos": df}
            else:
                # Excel: leer TODAS las hojas
                excel_file = pd.ExcelFile(BytesIO(content))
                sheet_names = excel_file.sheet_names
                sheets_data = {}
                for sheet_name in sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    # Solo incluir hojas con datos
                    if not df.empty and len(df.columns) > 0:
                        sheets_data[sheet_name] = df

            # Procesar cada hoja
            documents_created = []
            for sheet_name, df in sheets_data.items():
                # Limpiar nombres de columnas
                df.columns = [str(col).strip() for col in df.columns]
                # Eliminar filas completamente vacías
                df = df.dropna(how='all')

                if df.empty:
                    continue

                # Convertir a dict y limpiar NaN para JSON válido
                data = df.to_dict(orient='records')
                data = clean_nan_values(data)
                columns = list(df.columns)

                # Analizar campos con AI (opcional para uploads rápidos)
                if skip_ai:
                    ai_analysis = {
                        "data_type": "imported",
                        "detected_fields": {col: {"mapped_to": col, "type": "text"} for col in columns},
                        "summary": f"Importado directamente - {len(df)} filas",
                        "recommended_category": "general"
                    }
                else:
                    ai_analysis = await analyze_fields_with_ai(data, columns, f"{file.filename} - {sheet_name}")
                    ai_analysis = clean_nan_values(ai_analysis)

                # Crear documento en DB
                doc = models.Document(
                    filename=f"{file.filename}" if len(sheets_data) == 1 else f"{file.filename} [{sheet_name}]",
                    file_type="excel" if not filename.endswith('.csv') else "csv",
                    rows_count=len(df),
                    columns=columns,
                    period=detected_period,
                    status="pending_confirmation"
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)

                # Guardar datos raw con análisis AI
                raw_data = models.RawDocumentData(
                    document_id=doc.id,
                    raw_json={
                        "data": data,
                        "ai_analysis": ai_analysis,
                        "sheet_name": sheet_name
                    },
                    preview_data=data[:20]
                )
                db.add(raw_data)
                db.commit()

                documents_created.append({
                    "id": doc.id,
                    "filename": doc.filename,
                    "sheet_name": sheet_name,
                    "type": doc.file_type,
                    "rows": len(df),
                    "columns": columns,
                    "preview": data[:5],
                    "ai_analysis": ai_analysis,
                    "status": "pending_confirmation"
                })

            if not documents_created:
                raise HTTPException(status_code=400, detail="No se encontraron datos válidos en el archivo")

            return {
                "success": True,
                "message": f"Archivo '{file.filename}' procesado - {len(documents_created)} hoja(s) detectada(s)",
                "sheets_count": len(documents_created),
                "documents": documents_created
            }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/confirm")
async def confirm_upload(
    confirm_data: schemas.UploadConfirm,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Confirma un documento y lo guarda en el vault
    PROTEGIDO: Requiere autenticación
    """
    doc = db.query(models.Document).filter(models.Document.id == confirm_data.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Actualizar documento con metadata
    doc.store_id = confirm_data.store_id
    doc.store_name = confirm_data.store_name
    doc.period = confirm_data.period
    doc.uploaded_by = confirm_data.user_uid
    doc.status = "confirmed"

    db.commit()

    return {
        "success": True,
        "message": f"Documento guardado en vault: {doc.filename}",
        "document_id": doc.id
    }


@app.get("/documents")
async def list_documents(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    store_id: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Lista documentos del vault
    PROTEGIDO: Requiere autenticación
    """
    query = db.query(models.Document)

    if status:
        query = query.filter(models.Document.status == status)
    if store_id:
        query = query.filter(models.Document.store_id == store_id)

    docs = query.order_by(desc(models.Document.created_at)).limit(limit).all()

    return {
        "count": len(docs),
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "type": d.file_type,
                "store_id": d.store_id,
                "store_name": d.store_name,
                "period": d.period,
                "rows": d.rows_count,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in docs
        ]
    }


@app.get("/documents/{doc_id}")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene detalles de un documento
    PROTEGIDO: Requiere autenticación
    """
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    raw = db.query(models.RawDocumentData).filter(
        models.RawDocumentData.document_id == doc_id
    ).first()

    return {
        "id": doc.id,
        "filename": doc.filename,
        "type": doc.file_type,
        "store_id": doc.store_id,
        "store_name": doc.store_name,
        "period": doc.period,
        "rows": doc.rows_count,
        "columns": doc.columns,
        "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "preview": raw.preview_data if raw else [],
        "raw_text": raw.raw_text[:5000] if raw and raw.raw_text else None
    }


@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina un documento del vault
    PROTEGIDO: Requiere autenticación
    """
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Eliminar datos relacionados
    db.query(models.RawDocumentData).filter(
        models.RawDocumentData.document_id == doc_id
    ).delete()
    db.query(models.FinancialRecord).filter(
        models.FinancialRecord.document_id == doc_id
    ).delete()

    db.delete(doc)
    db.commit()

    return {"success": True, "message": f"Documento {doc_id} eliminado"}


# ============================================
# ANÁLISIS CON IA (FALLBACK AUTOMÁTICO)
# ============================================

@app.post("/analyze/{doc_id}")
async def analyze_document(
    doc_id: int,
    analysis_type: str = "general",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Analiza un documento con IA (OpenAI/Anthropic con fallback)
    PROTEGIDO: Requiere autenticación
    """
    if not openai_client and not anthropic_client:
        raise HTTPException(status_code=503, detail="No hay proveedores de IA configurados")

    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    raw = db.query(models.RawDocumentData).filter(
        models.RawDocumentData.document_id == doc_id
    ).first()

    try:
        if doc.file_type == "pdf":
            data_summary = f"""
            Archivo: {doc.filename}
            Sucursal: {doc.store_name or 'No especificada'}
            Periodo: {doc.period or 'No especificado'}
            Tipo: PDF (Estado de Resultados)

            Contenido:
            {raw.raw_text[:8000] if raw else 'Sin datos'}
            """
        else:
            df = pd.DataFrame(raw.raw_json) if raw and raw.raw_json else pd.DataFrame()
            data_summary = f"""
            Archivo: {doc.filename}
            Sucursal: {doc.store_name or 'No especificada'}
            Periodo: {doc.period or 'No especificado'}
            Filas: {len(df)}
            Columnas: {', '.join(df.columns.tolist()) if not df.empty else 'N/A'}

            Datos:
            {df.head(20).to_string() if not df.empty else 'Sin datos'}
            """

        prompts = {
            "general": f"""
            Analiza estos datos financieros de Little Caesars:

            {data_summary}

            Proporciona:
            1. Resumen ejecutivo (2-3 oraciones)
            2. Métricas clave identificadas
            3. Tendencias o patrones notables
            4. Alertas o áreas de preocupación
            5. Recomendaciones

            Responde en español.
            """,

            "pl": f"""
            Analiza este estado de resultados (P&L) de Little Caesars:

            {data_summary}

            Calcula:
            1. Ventas totales
            2. Costo de ventas y margen bruto
            3. Gastos operativos desglosados
            4. Utilidad neta y margen neto
            5. Alertas sobre gastos excesivos

            Responde en español con números en pesos mexicanos.
            """
        }

        prompt = prompts.get(analysis_type, prompts["general"])

        # Usar helper con fallback automático
        messages = [
            {"role": "system", "content": "Eres Julia, experta en análisis financiero para restaurantes Little Caesars. Respondes en español de manera profesional."},
            {"role": "user", "content": prompt}
        ]
        ai_response = call_ai_with_fallback(messages, max_tokens=2000, temperature=0.7)

        # Guardar análisis en DB
        analysis = models.Analysis(
            document_id=doc_id,
            store_id=doc.store_id,
            analysis_type=analysis_type,
            query=f"Análisis {analysis_type}",
            result=ai_response["response"],
            tokens_used=ai_response["tokens_used"]
        )
        db.add(analysis)
        db.commit()

        return {
            "success": True,
            "analysis": {
                "doc_id": doc_id,
                "filename": doc.filename,
                "type": analysis_type,
                "result": ai_response["response"],
                "tokens_used": ai_response["tokens_used"],
                "provider": ai_response["provider"]
            }
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CHAT CON JULIA
# ============================================

@app.post("/chat")
async def chat_with_julia(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Chat con Julia - consultas en lenguaje natural
    PROTEGIDO: Requiere autenticación
    Usa fallback automático entre OpenAI y Anthropic
    """
    # Verificar que hay al menos un proveedor de IA
    if not openai_client and not anthropic_client:
        raise HTTPException(status_code=503, detail="No hay proveedores de IA configurados")

    try:
        # Construir contexto con datos del vault
        data_context = request.context or ""

        # Obtener documentos confirmados
        docs_query = db.query(models.Document).filter(
            models.Document.status == "confirmed"
        )
        if request.store_id:
            docs_query = docs_query.filter(models.Document.store_id == request.store_id)

        docs = docs_query.order_by(desc(models.Document.created_at)).limit(10).all()

        if docs:
            data_context += "\n\nDocumentos en el vault:\n"
            for doc in docs:
                data_context += f"- {doc.filename}: {doc.store_name or 'Sin sucursal'}, {doc.period or 'Sin periodo'}, {doc.rows_count} filas\n"

                # Incluir preview de datos
                raw = db.query(models.RawDocumentData).filter(
                    models.RawDocumentData.document_id == doc.id
                ).first()

                if raw:
                    if doc.file_type == "pdf" and raw.raw_text:
                        data_context += f"  Contenido:\n{raw.raw_text[:3000]}\n"
                    elif raw.preview_data:
                        data_context += f"  Datos: {json.dumps(raw.preview_data[:5], ensure_ascii=False)}\n"

        # Obtener resúmenes mensuales si existen
        summaries = db.query(models.MonthlySummary).order_by(
            desc(models.MonthlySummary.period)
        ).limit(5).all()

        if summaries:
            data_context += "\n\nResúmenes mensuales:\n"
            for s in summaries:
                data_context += f"- {s.store_name} ({s.period}): Ventas ${s.total_sales:,.2f}, Utilidad ${s.net_profit:,.2f}\n"

        messages = [
            {
                "role": "system",
                "content": f"""Eres Julia, asistente experta en análisis financiero para Little Caesars México.

Tu personalidad:
- Profesional pero amigable
- Respondes siempre en español
- Das respuestas claras y accionables
- Formateas números en pesos mexicanos
- Cuando detectas problemas, sugieres soluciones

Datos disponibles:
{data_context}

Si no tienes datos suficientes, sugiere amablemente que suban los documentos necesarios.
"""
            }
        ]

        # Agregar historial
        for msg in (request.history or [])[-6:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        messages.append({"role": "user", "content": request.message})

        # Usar helper con fallback automático
        ai_response = call_ai_with_fallback(messages, max_tokens=1500, temperature=0.7)

        # Guardar en análisis
        analysis = models.Analysis(
            store_id=request.store_id,
            analysis_type="chat",
            query=request.message,
            result=ai_response["response"],
            tokens_used=ai_response["tokens_used"]
        )
        db.add(analysis)
        db.commit()

        return {
            "success": True,
            "response": ai_response["response"],
            "tokens_used": ai_response["tokens_used"],
            "provider": ai_response["provider"]
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# VAULT - Resumen y Queries
# ============================================

@app.get("/vault/summary")
async def get_vault_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Resumen del vault
    PROTEGIDO: Requiere autenticación
    """
    total_docs = db.query(models.Document).filter(
        models.Document.status == "confirmed"
    ).count()

    # Contar por tipo
    type_counts = db.query(
        models.Document.file_type,
        func.count(models.Document.id)
    ).filter(
        models.Document.status == "confirmed"
    ).group_by(models.Document.file_type).all()

    # Sucursales únicas
    stores = db.query(models.Document.store_id).filter(
        models.Document.status == "confirmed",
        models.Document.store_id.isnot(None)
    ).distinct().count()

    # Documentos recientes
    recent = db.query(models.Document).filter(
        models.Document.status == "confirmed"
    ).order_by(desc(models.Document.created_at)).limit(5).all()

    return {
        "total_documents": total_docs,
        "total_stores": stores,
        "documents_by_type": {t[0]: t[1] for t in type_counts},
        "recent_documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "store_name": d.store_name,
                "period": d.period,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in recent
        ]
    }


@app.get("/vault/stores")
async def get_stores(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista sucursales con datos
    PROTEGIDO: Requiere autenticación
    """
    stores = db.query(
        models.Document.store_id,
        models.Document.store_name,
        func.count(models.Document.id).label("doc_count")
    ).filter(
        models.Document.status == "confirmed",
        models.Document.store_id.isnot(None)
    ).group_by(
        models.Document.store_id,
        models.Document.store_name
    ).all()

    return {
        "count": len(stores),
        "stores": [
            {"store_id": s[0], "store_name": s[1], "documents": s[2]}
            for s in stores
        ]
    }


@app.get("/analyses")
async def list_analyses(
    db: Session = Depends(get_db),
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """
    Lista análisis realizados
    PROTEGIDO: Requiere autenticación
    """
    analyses = db.query(models.Analysis).order_by(
        desc(models.Analysis.created_at)
    ).limit(limit).all()

    return {
        "count": len(analyses),
        "analyses": [
            {
                "id": a.id,
                "type": a.analysis_type,
                "query": a.query[:100] if a.query else None,
                "store_id": a.store_id,
                "tokens_used": a.tokens_used,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in analyses
        ]
    }


# ============================================
# DASHBOARD - Estadísticas para el frontend
# ============================================

@app.get("/dashboard/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Estadísticas para el dashboard principal
    PROTEGIDO: Requiere autenticación
    """

    # Total documentos confirmados
    total_docs = db.query(models.Document).filter(
        models.Document.status == "confirmed"
    ).count()

    # Total sucursales únicas
    total_stores = db.query(models.Document.store_id).filter(
        models.Document.status == "confirmed",
        models.Document.store_id.isnot(None)
    ).distinct().count()

    # Total análisis realizados
    total_analyses = db.query(models.Analysis).count()

    # Documentos por tipo
    type_counts = db.query(
        models.Document.file_type,
        func.count(models.Document.id)
    ).filter(
        models.Document.status == "confirmed"
    ).group_by(models.Document.file_type).all()

    # Documentos recientes (últimos 5)
    recent_docs = db.query(models.Document).filter(
        models.Document.status == "confirmed"
    ).order_by(desc(models.Document.created_at)).limit(5).all()

    # Sucursales con más documentos
    top_stores = db.query(
        models.Document.store_id,
        models.Document.store_name,
        func.count(models.Document.id).label("doc_count")
    ).filter(
        models.Document.status == "confirmed",
        models.Document.store_id.isnot(None)
    ).group_by(
        models.Document.store_id,
        models.Document.store_name
    ).order_by(desc("doc_count")).limit(5).all()

    # Resúmenes mensuales si existen
    monthly_data = db.query(models.MonthlySummary).order_by(
        desc(models.MonthlySummary.period)
    ).limit(6).all()

    return {
        "total_documents": total_docs,
        "total_stores": total_stores,
        "total_analyses": total_analyses,
        "documents_by_type": {
            t[0] if t[0] else "otros": t[1] for t in type_counts
        },
        "recent_documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "store_name": d.store_name,
                "period": d.period,
                "type": d.file_type,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in recent_docs
        ],
        "top_stores": [
            {
                "store_id": s[0],
                "store_name": s[1],
                "documents": s[2]
            }
            for s in top_stores
        ],
        "monthly_summaries": [
            {
                "period": m.period,
                "store_name": m.store_name,
                "total_sales": m.total_sales,
                "net_profit": m.net_profit,
                "gross_margin": m.gross_margin,
                "net_margin": m.net_margin
            }
            for m in monthly_data
        ] if monthly_data else []
    }


# ============================================
# CHARTS - Datos para gráficas en vivo
# ============================================

@app.get("/charts/financial")
async def get_charts_financial_data(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Extrae datos financieros de los documentos para las gráficas
    PROTEGIDO: Requiere autenticación
    """

    # Buscar documentos de Estado de Resultados confirmados
    docs = db.query(models.Document).filter(
        models.Document.status == "confirmed",
        models.Document.filename.ilike("%ESTADO DE RESULTADOS%")
    ).order_by(desc(models.Document.created_at)).limit(5).all()

    stores_data = {}
    total_ingresos = 0
    total_egresos = 0
    categories = {}

    for doc in docs:
        raw = db.query(models.RawDocumentData).filter(
            models.RawDocumentData.document_id == doc.id
        ).first()

        if not raw or not raw.raw_json:
            continue

        data = raw.raw_json.get("data", [])
        if not data:
            continue

        # Primera fila tiene nombres de tiendas
        header_row = data[0] if data else {}

        # Extraer nombres de tiendas (columnas impares que no son %)
        store_names = []
        for key, val in header_row.items():
            if val and isinstance(val, str) and val != "%" and "Unnamed" not in key:
                store_names.append(val)

        # Buscar filas de INGRESOS, EGRESOS, UTILIDAD
        for row in data:
            first_col = list(row.values())[0] if row else None
            if not first_col:
                continue

            first_col_str = str(first_col).upper().strip()

            # Extraer valores por tienda
            col_idx = 0
            for key, val in row.items():
                if "Unnamed" in key or not val:
                    continue
                if isinstance(val, (int, float)) and col_idx < len(store_names):
                    store_name = store_names[col_idx] if col_idx < len(store_names) else f"Tienda {col_idx}"

                    if store_name not in stores_data:
                        stores_data[store_name] = {"ingresos": 0, "egresos": 0, "utilidad": 0}

                    if first_col_str == "INGRESOS" or "VENTA" in first_col_str:
                        stores_data[store_name]["ingresos"] = val
                        total_ingresos += val
                    elif first_col_str == "TOTAL EGRESOS" or first_col_str == "EGRESOS":
                        stores_data[store_name]["egresos"] = val
                        total_egresos += val
                    elif "UTILIDAD" in first_col_str and "NETA" in first_col_str:
                        stores_data[store_name]["utilidad"] = val

                    # Categorizar gastos
                    if any(x in first_col_str for x in ["NOMINA", "SALARIO", "SUELDO"]):
                        categories["Nómina"] = categories.get("Nómina", 0) + val
                    elif any(x in first_col_str for x in ["RENTA", "ALQUILER"]):
                        categories["Renta"] = categories.get("Renta", 0) + val
                    elif any(x in first_col_str for x in ["LUZ", "ELECTRICIDAD", "CFE"]):
                        categories["Servicios"] = categories.get("Servicios", 0) + val
                    elif any(x in first_col_str for x in ["COSTO", "INGREDIENTE", "MATERIA"]):
                        categories["Costo de Venta"] = categories.get("Costo de Venta", 0) + val

                col_idx += 1

    # Preparar datos para gráficas
    stores_list = list(stores_data.keys())[:10]  # Top 10 tiendas
    ventas_por_tienda = [stores_data.get(s, {}).get("ingresos", 0) for s in stores_list]
    utilidad_por_tienda = [stores_data.get(s, {}).get("utilidad", 0) for s in stores_list]

    return {
        "success": True,
        "summary": {
            "total_ingresos": total_ingresos,
            "total_egresos": total_egresos,
            "utilidad_bruta": total_ingresos - total_egresos,
            "margen": ((total_ingresos - total_egresos) / total_ingresos * 100) if total_ingresos > 0 else 0,
            "num_tiendas": len(stores_data),
            "num_documentos": len(docs)
        },
        "stores": {
            "names": stores_list,
            "ventas": ventas_por_tienda,
            "utilidad": utilidad_por_tienda
        },
        "categories": categories,
        "raw_stores": stores_data
    }


# ============================================
# STATIC FILES - Servir frontend HTML
# ============================================

# Ruta al directorio de archivos estáticos (root del proyecto)
import pathlib
STATIC_DIR = pathlib.Path(__file__).parent.parent

# Servir index.html en la raíz
@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

# Friendly URLs - rutas explícitas para cada página
@app.get("/subir", response_class=FileResponse)
async def serve_upload():
    return FileResponse(STATIC_DIR / "upload.html")

@app.get("/julia", response_class=FileResponse)
async def serve_julia():
    return FileResponse(STATIC_DIR / "julia.html")

@app.get("/vault", response_class=FileResponse)
async def serve_documents():
    return FileResponse(STATIC_DIR / "documents.html")

@app.get("/graficas", response_class=FileResponse)
async def serve_graficas():
    return FileResponse(STATIC_DIR / "graficas.html")

@app.get("/reportes", response_class=FileResponse)
async def serve_reports():
    return FileResponse(STATIC_DIR / "reports.html")

@app.get("/config", response_class=FileResponse)
async def serve_settings():
    return FileResponse(STATIC_DIR / "settings.html")

@app.get("/login", response_class=FileResponse)
async def serve_login():
    return FileResponse(STATIC_DIR / "login.html")

# También servir archivos .html directamente
@app.get("/{filename}.html", response_class=FileResponse)
async def serve_html(filename: str):
    file_path = STATIC_DIR / f"{filename}.html"
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Page not found")


# Punto de entrada
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
