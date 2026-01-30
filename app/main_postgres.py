"""
CICLOPS Backend - Producción con PostgreSQL
API para análisis financiero de Little Caesars
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, Request, Header, status, Body
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
import re
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import engine, get_db, Base
from . import db_models as models
from . import schemas
from collections import defaultdict
import time
import logging

# Cargar variables de entorno
load_dotenv()


# ============================================
# LOGGING DE AUDITORÍA
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
audit_logger = logging.getLogger("audit")


def log_audit(action: str, user_id: str = None, ip: str = None, details: str = None):
    """Registra eventos de auditoría para seguridad"""
    msg = f"[AUDIT] {action}"
    if user_id:
        msg += f" | user={user_id}"
    if ip:
        msg += f" | ip={ip}"
    if details:
        msg += f" | {details}"
    audit_logger.info(msg)


# ============================================
# RATE LIMITER SIMPLE (en memoria)
# ============================================
class RateLimiter:
    """Limitador de tasa para prevenir ataques de fuerza bruta"""
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, identifier: str) -> bool:
        """Verifica si el identificador puede hacer otra request"""
        now = time.time()
        # Limpiar requests viejas
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.window_seconds
        ]
        # Verificar límite
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        self.requests[identifier].append(now)
        return True

    def get_retry_after(self, identifier: str) -> int:
        """Retorna segundos hasta que pueda intentar de nuevo"""
        if not self.requests[identifier]:
            return 0
        oldest = min(self.requests[identifier])
        return max(0, int(self.window_seconds - (time.time() - oldest)))


# Rate limiters para diferentes endpoints
login_limiter = RateLimiter(max_requests=5, window_seconds=60)      # 5 intentos por minuto
upload_limiter = RateLimiter(max_requests=10, window_seconds=60)    # 10 uploads por minuto
chat_limiter = RateLimiter(max_requests=20, window_seconds=60)      # 20 chats por minuto

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


# Middleware de seguridad - Headers de protección
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevenir clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevenir MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Habilitar XSS filter del navegador
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Forzar HTTPS por 1 año
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Política de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permisos de funciones del navegador
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


# Agregar middleware (orden importa: HTTPS primero, luego seguridad)
app.add_middleware(ForceHTTPSMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    print(f"🎫 Token creado con SECRET_KEY: {SECRET_KEY[:10]}...")
    return token


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
        print(f"🔍 Verificando token: {token[:20]}...")
        print(f"🔐 Usando SECRET_KEY: {SECRET_KEY[:10]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"✅ Token válido, payload: {payload}")
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        user_id = int(user_id_str)
    except JWTError as e:
        print(f"❌ Error JWT: {e}")
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
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = int(user_id_str)

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
    token = create_access_token(data={"sub": str(user.id)})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }


# Código de acceso único (temporal)
ACCESS_CODE = "LC-2026-X7K9M"

@app.post("/auth/code-login")
async def code_login(request: Request, code: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Login con código de acceso único - Rate limited"""
    # Rate limiting por IP
    client_ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    if not login_limiter.is_allowed(client_ip):
        retry_after = login_limiter.get_retry_after(client_ip)
        log_audit("LOGIN_RATE_LIMITED", ip=client_ip, details="Demasiados intentos")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos. Intenta en {retry_after} segundos.",
            headers={"Retry-After": str(retry_after)}
        )

    if code != ACCESS_CODE:
        log_audit("LOGIN_FAILED", ip=client_ip, details="Código incorrecto")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de acceso incorrecto"
        )

    # Buscar o crear usuario genérico
    user = db.query(models.User).filter(models.User.email == "admin@ciclops.mx").first()
    if not user:
        # Crear usuario admin si no existe
        user = models.User(
            email="admin@ciclops.mx",
            name="Admin CICLOPS",
            hashed_password=get_password_hash("temp-not-used"),
            role="admin",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    log_audit("LOGIN_SUCCESS", user_id=str(user.id), ip=client_ip)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active
        }
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

    token = create_access_token(data={"sub": str(user.id)})

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

        token = create_access_token(data={"sub": str(user.id)})
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
            # Excel o CSV - Combinar todas las hojas en UN solo documento
            all_dfs = []
            sheets_info = []

            if filename.endswith('.csv'):
                df = pd.read_csv(BytesIO(content))
                df.columns = [str(col).strip() for col in df.columns]
                df = df.dropna(how='all')
                if not df.empty:
                    all_dfs.append(df)
                    sheets_info.append({"name": "Datos", "rows": len(df)})
            else:
                # Excel: leer TODAS las hojas y combinarlas
                excel_file = pd.ExcelFile(BytesIO(content))
                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    df.columns = [str(col).strip() for col in df.columns]
                    df = df.dropna(how='all')
                    if not df.empty and len(df.columns) > 0:
                        # Agregar columna para identificar la hoja de origen
                        df['_hoja_origen'] = sheet_name
                        all_dfs.append(df)
                        sheets_info.append({"name": sheet_name, "rows": len(df)})

            if not all_dfs:
                raise HTTPException(status_code=400, detail="No se encontraron datos válidos en el archivo")

            # Combinar todos los DataFrames
            combined_df = pd.concat(all_dfs, ignore_index=True, sort=False)

            # Convertir a dict y limpiar NaN
            data = combined_df.to_dict(orient='records')
            data = clean_nan_values(data)
            columns = list(combined_df.columns)

            # Analizar con AI
            if skip_ai:
                ai_analysis = {
                    "data_type": "imported",
                    "detected_fields": {col: {"mapped_to": col, "type": "text"} for col in columns},
                    "summary": f"Importado - {len(combined_df)} filas de {len(sheets_info)} hoja(s)",
                    "recommended_category": "general",
                    "sheets_combined": sheets_info
                }
            else:
                ai_analysis = await analyze_fields_with_ai(data, columns, file.filename)
                ai_analysis = clean_nan_values(ai_analysis)
                ai_analysis["sheets_combined"] = sheets_info

            # Crear UN solo documento
            doc = models.Document(
                filename=file.filename,
                file_type="excel" if not filename.endswith('.csv') else "csv",
                rows_count=len(combined_df),
                columns=columns,
                period=detected_period,
                status="pending_confirmation"
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            # Guardar datos raw
            raw_data = models.RawDocumentData(
                document_id=doc.id,
                raw_json={
                    "data": data,
                    "ai_analysis": ai_analysis,
                    "sheets_combined": sheets_info
                },
                preview_data=data[:20]
            )
            db.add(raw_data)
            db.commit()

            return {
                "success": True,
                "message": f"Archivo '{file.filename}' procesado - {len(sheets_info)} hoja(s) combinadas, {len(combined_df)} filas totales",
                "sheets_count": 1,
                "documents": [{
                    "id": doc.id,
                    "filename": doc.filename,
                    "type": doc.file_type,
                    "rows": len(combined_df),
                    "columns": columns,
                    "preview": data[:5],
                    "ai_analysis": ai_analysis,
                    "sheets_combined": sheets_info,
                    "status": "pending_confirmation"
                }]
            }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# EXTRACCIÓN DE DATOS FINANCIEROS A SUMMARIES
# ============================================

def extract_financial_data_to_summaries(doc_id: int, db: Session) -> dict:
    """
    Extrae datos financieros de un documento confirmado y los guarda en monthly_summaries.
    Retorna estadísticas del proceso.
    """
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        return {"success": False, "error": "Documento no encontrado"}

    raw = db.query(models.RawDocumentData).filter(
        models.RawDocumentData.document_id == doc_id
    ).first()

    if not raw or not raw.raw_json:
        return {"success": False, "error": "Sin datos raw"}

    data = raw.raw_json.get("data", [])
    if not data:
        return {"success": False, "error": "Datos vacíos"}

    # Extraer período del nombre del archivo (P11, P12, P13, etc.)
    period_match = re.search(r'P(\d+)', doc.filename)
    period_num = period_match.group(1) if period_match else "00"
    period_label = f"2025-P{period_num}"  # Formato: 2025-P11, 2025-P12, etc.

    # Primera fila tiene nombres de tiendas
    header_row = data[0] if data else {}

    # Mapear columnas a tiendas
    store_columns = {}  # {col_key: store_name}
    # Nombres a excluir (son hojas de Excel, no tiendas)
    excluded_names = ["EDO RES", "EDO RESUL", "TOTAL", "COMENTARIOS", "FLETES", "PUBLICIDAD", "COLABORADORES"]

    for key, val in header_row.items():
        if val and isinstance(val, str) and val != "%" and "Unnamed" not in key and "_hoja" not in key:
            # Limpiar nombre de tienda
            store_name = str(val).strip().upper()
            # Excluir nombres de hojas y valores no válidos
            if store_name and len(store_name) > 1:
                is_excluded = any(exc in store_name for exc in excluded_names)
                if not is_excluded:
                    store_columns[key] = store_name

    # Estructura para acumular datos por tienda
    stores_data = {}
    for col_key, store_name in store_columns.items():
        stores_data[store_name] = {
            "store_id": store_name.replace(" ", "_").lower(),
            "store_name": store_name,
            "total_sales": 0,
            "cost_of_sales": 0,
            "operating_expenses": 0,
            "labor_cost": 0,
            "rent": 0,
            "utilities": 0,
            "net_profit": 0,
            "col_key": col_key
        }

    # Recorrer filas buscando conceptos financieros
    for row in data[1:]:  # Saltar header
        first_col_val = None
        for key, val in row.items():
            # Buscar el concepto en la primera columna válida (no metadata, no Unnamed)
            if val and isinstance(val, str) and "Unnamed" not in key and "_hoja" not in key and "P" in key:
                first_col_val = str(val).upper().strip()
                break

        if not first_col_val:
            continue

        # Ignorar si es un nombre de hoja, no un concepto
        if any(exc in first_col_val for exc in ["EDO RES", "EDO RESUL"]):
            continue

        # Extraer valores por tienda
        for store_name, store_info in stores_data.items():
            col_key = store_info["col_key"]
            val = row.get(col_key)

            if val is None or not isinstance(val, (int, float)):
                continue

            val = float(val)

            # Clasificar según el concepto
            if first_col_val == "INGRESOS" or first_col_val == "VENTAS" or "VENTA NETA" in first_col_val:
                store_info["total_sales"] = val
            elif first_col_val == "COSTO DE VENTA" or first_col_val == "COSTO DE VENTAS":
                store_info["cost_of_sales"] = val
            elif first_col_val == "TOTAL EGRESOS" or first_col_val == "EGRESOS TOTALES":
                store_info["operating_expenses"] = val
            elif "NOMINA" in first_col_val or "SALARIO" in first_col_val or "SUELDO" in first_col_val:
                store_info["labor_cost"] += val
            elif "RENTA" in first_col_val and "LOCAL" in first_col_val:
                store_info["rent"] = val
            elif first_col_val == "RENTA":
                store_info["rent"] = val
            elif any(x in first_col_val for x in ["CFE", "LUZ", "ELECTRICIDAD", "AGUA", "GAS"]):
                store_info["utilities"] += val
            elif "UTILIDAD NETA" in first_col_val or first_col_val == "UTILIDAD":
                store_info["net_profit"] = val

    # Guardar en monthly_summaries
    records_created = 0
    records_updated = 0

    for store_name, store_info in stores_data.items():
        # Verificar si ya existe
        existing = db.query(models.MonthlySummary).filter(
            models.MonthlySummary.store_id == store_info["store_id"],
            models.MonthlySummary.period == period_label
        ).first()

        # Calcular márgenes
        gross_profit = store_info["total_sales"] - store_info["cost_of_sales"]
        gross_margin = (gross_profit / store_info["total_sales"] * 100) if store_info["total_sales"] > 0 else 0
        net_margin = (store_info["net_profit"] / store_info["total_sales"] * 100) if store_info["total_sales"] > 0 else 0

        if existing:
            # Actualizar
            existing.total_sales = store_info["total_sales"]
            existing.cost_of_sales = store_info["cost_of_sales"]
            existing.gross_profit = gross_profit
            existing.gross_margin = gross_margin
            existing.operating_expenses = store_info["operating_expenses"]
            existing.labor_cost = store_info["labor_cost"]
            existing.rent = store_info["rent"]
            existing.utilities = store_info["utilities"]
            existing.net_profit = store_info["net_profit"]
            existing.net_margin = net_margin
            existing.document_id = doc_id
            records_updated += 1
        else:
            # Crear nuevo
            summary = models.MonthlySummary(
                store_id=store_info["store_id"],
                store_name=store_info["store_name"],
                period=period_label,
                total_sales=store_info["total_sales"],
                cost_of_sales=store_info["cost_of_sales"],
                gross_profit=gross_profit,
                gross_margin=gross_margin,
                operating_expenses=store_info["operating_expenses"],
                labor_cost=store_info["labor_cost"],
                rent=store_info["rent"],
                utilities=store_info["utilities"],
                net_profit=store_info["net_profit"],
                net_margin=net_margin,
                document_id=doc_id
            )
            db.add(summary)
            records_created += 1

    db.commit()

    return {
        "success": True,
        "document_id": doc_id,
        "period": period_label,
        "stores_processed": len(stores_data),
        "records_created": records_created,
        "records_updated": records_updated
    }


@app.post("/process/sync-summaries")
async def sync_financial_summaries(
    db: Session = Depends(get_db),
    clean: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Procesa todos los documentos confirmados y extrae datos a monthly_summaries.
    PROTEGIDO: Requiere autenticación
    Parámetro clean=true borra todos los registros existentes antes de procesar.
    """
    deleted_count = 0
    if clean:
        # Borrar todos los registros existentes de monthly_summaries
        deleted_count = db.query(models.MonthlySummary).delete()
        db.commit()

    # Buscar documentos confirmados de Estado de Resultados
    docs = db.query(models.Document).filter(
        models.Document.status == "confirmed",
        models.Document.filename.ilike("%ESTADO DE RESULTADOS%")
    ).all()

    results = []
    for doc in docs:
        result = extract_financial_data_to_summaries(doc.id, db)
        results.append({
            "document_id": doc.id,
            "filename": doc.filename,
            **result
        })

    return {
        "success": True,
        "cleaned": clean,
        "deleted_records": deleted_count,
        "documents_processed": len(docs),
        "results": results
    }


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

    # Procesar datos financieros automáticamente si es Estado de Resultados
    extraction_result = None
    if "ESTADO DE RESULTADOS" in doc.filename.upper():
        extraction_result = extract_financial_data_to_summaries(doc.id, db)

    return {
        "success": True,
        "message": f"Documento guardado en vault: {doc.filename}",
        "document_id": doc.id,
        "financial_extraction": extraction_result
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
# CHARTS DASHBOARD - Datos para TODAS las gráficas
# ============================================

@app.get("/api/charts/dashboard")
async def get_dashboard_charts_data(
    db: Session = Depends(get_db),
    period: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint consolidado que retorna TODOS los datos necesarios
    para las 10 gráficas del dashboard con datos REALES.
    PROTEGIDO: Requiere autenticación
    """
    try:
        # 1. Verificar si hay datos en monthly_summaries
        summary_count = db.query(models.MonthlySummary).count()

        if summary_count == 0:
            return {
                "success": True,
                "has_data": False,
                "message": "No hay datos financieros. Sube documentos para ver gráficas."
            }

        # 2. Obtener periodos disponibles
        periods_query = db.query(
            models.MonthlySummary.period
        ).distinct().order_by(
            desc(models.MonthlySummary.period)
        ).limit(12).all()

        available_periods = [p[0] for p in periods_query]
        current_period = period or (available_periods[0] if available_periods else None)
        previous_period = available_periods[1] if len(available_periods) > 1 else None

        # 3. === revenueChart: Ingresos vs Utilidad por Tienda ===
        store_data = db.query(
            models.MonthlySummary.store_id,
            models.MonthlySummary.store_name,
            models.MonthlySummary.total_sales,
            models.MonthlySummary.net_profit,
            models.MonthlySummary.net_margin
        ).filter(
            models.MonthlySummary.period == current_period
        ).order_by(
            desc(models.MonthlySummary.total_sales)
        ).limit(7).all()

        revenue_chart = {
            "labels": [s.store_name or s.store_id or f"Tienda {i+1}" for i, s in enumerate(store_data)],
            "datasets": {
                "ingresos": [float(s.total_sales or 0) for s in store_data],
                "utilidad": [float(s.net_profit or 0) for s in store_data]
            }
        }

        # 4. === Totales del periodo actual ===
        totals_current = db.query(
            func.sum(models.MonthlySummary.total_sales).label('sales'),
            func.sum(models.MonthlySummary.operating_expenses).label('expenses'),
            func.sum(models.MonthlySummary.labor_cost).label('labor'),
            func.sum(models.MonthlySummary.cost_of_sales).label('cost_of_sales'),
            func.sum(models.MonthlySummary.rent).label('rent'),
            func.sum(models.MonthlySummary.utilities).label('utilities'),
            func.sum(models.MonthlySummary.net_profit).label('profit')
        ).filter(
            models.MonthlySummary.period == current_period
        ).first()

        total_sales = float(totals_current.sales or 0)
        total_expenses = float(totals_current.expenses or 0)
        total_labor = float(totals_current.labor or 0)
        total_cost_of_sales = float(totals_current.cost_of_sales or 0)
        total_rent = float(totals_current.rent or 0)
        total_utilities = float(totals_current.utilities or 0)
        total_profit = float(totals_current.profit or 0)

        # 5. === expenseChart: Principales Gastos ===
        expense_labels = ["Nómina", "Costo de Venta", "Renta", "Servicios"]
        expense_values = [total_labor, total_cost_of_sales, total_rent, total_utilities]

        # Agregar "Otros" si hay diferencia
        otros = total_expenses - sum(expense_values)
        if otros > 0:
            expense_labels.append("Otros")
            expense_values.append(otros)

        expense_chart = {
            "labels": expense_labels,
            "values": expense_values
        }

        # 6. === trendChart: Tendencia 6 meses ===
        trend_periods = available_periods[:6][::-1]  # Últimos 6, ordenados ascendente
        trend_data = []
        for p in trend_periods:
            totals = db.query(
                func.sum(models.MonthlySummary.total_sales).label('sales'),
                func.sum(models.MonthlySummary.net_profit).label('profit')
            ).filter(
                models.MonthlySummary.period == p
            ).first()
            trend_data.append({
                "period": p,
                "sales": float(totals.sales or 0),
                "profit": float(totals.profit or 0)
            })

        trend_chart = {
            "labels": [t["period"] for t in trend_data],
            "datasets": {
                "ventas": [t["sales"] for t in trend_data],
                "utilidad": [t["profit"] for t in trend_data]
            }
        }

        # 7. === correlationChart: Ingresos vs Gastos por tienda ===
        correlation_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.total_sales,
            models.MonthlySummary.operating_expenses
        ).filter(
            models.MonthlySummary.period == current_period
        ).all()

        sales_list = [float(c.total_sales or 0) for c in correlation_data]
        expenses_list = [float(c.operating_expenses or 0) for c in correlation_data]

        # Calcular correlación
        correlation_coef = 0.0
        if len(sales_list) >= 2 and len(expenses_list) >= 2:
            try:
                correlation_coef = float(np.corrcoef(sales_list, expenses_list)[0, 1])
                if np.isnan(correlation_coef):
                    correlation_coef = 0.0
            except Exception:
                correlation_coef = 0.0

        correlation_chart = {
            "points": [
                {"x": float(c.total_sales or 0), "y": float(c.operating_expenses or 0), "label": c.store_name or ""}
                for c in correlation_data
            ],
            "correlation_coefficient": round(correlation_coef, 2)
        }

        # 8. === expenseDistChart: Distribución % ===
        total_expense_sum = sum(expense_values) if expense_values else 1
        expense_dist_chart = {
            "labels": expense_labels,
            "values": [round(v / total_expense_sum * 100, 1) if total_expense_sum > 0 else 0 for v in expense_values],
            "amounts": expense_values
        }

        # 9. === efficiencyChart: Eficiencia Operativa ===
        efficiency_value = 0.0
        if total_sales > 0:
            efficiency_value = ((total_sales - total_expenses) / total_sales) * 100

        efficiency_chart = {
            "value": round(max(0, min(100, efficiency_value)), 1),
            "target": 85,
            "industry_avg": 72
        }

        # 10. === compareChart: vs Mes Anterior ===
        compare_chart = None
        if previous_period:
            totals_prev = db.query(
                func.sum(models.MonthlySummary.total_sales).label('sales'),
                func.sum(models.MonthlySummary.operating_expenses).label('expenses'),
                func.sum(models.MonthlySummary.net_profit).label('profit')
            ).filter(
                models.MonthlySummary.period == previous_period
            ).first()

            prev_sales = float(totals_prev.sales or 0)
            prev_expenses = float(totals_prev.expenses or 0)
            prev_profit = float(totals_prev.profit or 0)

            def calc_change(current, previous):
                if previous and previous > 0:
                    return round(((current - previous) / previous) * 100, 1)
                return 0

            compare_chart = {
                "labels": ["Ventas", "Gastos", "Utilidad"],
                "current": [total_sales, total_expenses, total_profit],
                "previous": [prev_sales, prev_expenses, prev_profit],
                "change_percent": [
                    calc_change(total_sales, prev_sales),
                    calc_change(total_expenses, prev_expenses),
                    calc_change(total_profit, prev_profit)
                ]
            }

        # 11. === topCategoriesChart: Top 5 gastos ===
        # Intentar obtener de financial_records si hay datos
        top_from_records = db.query(
            models.FinancialRecord.subcategory,
            func.sum(models.FinancialRecord.amount).label('total')
        ).filter(
            models.FinancialRecord.category.in_(['gastos', 'costos']),
            models.FinancialRecord.period == current_period
        ).group_by(
            models.FinancialRecord.subcategory
        ).order_by(
            desc('total')
        ).limit(5).all()

        if top_from_records:
            top_categories_chart = {
                "labels": [c.subcategory or "Otros" for c in top_from_records],
                "values": [float(c.total or 0) for c in top_from_records]
            }
        else:
            # Fallback a expense_chart
            sorted_expenses = sorted(zip(expense_labels, expense_values), key=lambda x: x[1], reverse=True)[:5]
            top_categories_chart = {
                "labels": [x[0] for x in sorted_expenses],
                "values": [x[1] for x in sorted_expenses]
            }

        # 12. === rankingChart: Ranking por rentabilidad ===
        ranking_data = db.query(
            models.MonthlySummary.store_id,
            models.MonthlySummary.store_name,
            models.MonthlySummary.net_margin
        ).filter(
            models.MonthlySummary.period == current_period
        ).order_by(
            desc(models.MonthlySummary.net_margin)
        ).limit(7).all()

        def get_status(margin):
            if margin >= 20:
                return "excellent"
            elif margin >= 15:
                return "good"
            elif margin >= 10:
                return "warning"
            return "critical"

        ranking_chart = {
            "labels": [r.store_name or r.store_id or f"Tienda" for r in ranking_data],
            "margins": [round(float(r.net_margin or 0), 1) for r in ranking_data],
            "status": [get_status(r.net_margin or 0) for r in ranking_data]
        }

        # 13. === radarChart: Métricas de Salud ===
        avg_margin = sum(r.net_margin or 0 for r in ranking_data) / len(ranking_data) if ranking_data else 0
        growth_rate = compare_chart["change_percent"][0] if compare_chart else 0

        def normalize(value, min_v, max_v):
            if max_v == min_v:
                return 50
            return min(100, max(0, ((value - min_v) / (max_v - min_v)) * 100))

        radar_chart = {
            "labels": ["Ventas", "Margen", "Eficiencia", "Crecimiento", "Consistencia"],
            "values": [
                round(normalize(total_sales, 0, total_sales * 1.5), 0) if total_sales > 0 else 50,
                round(normalize(avg_margin, 5, 30), 0),
                round(efficiency_chart["value"], 0),
                round(normalize(growth_rate, -20, 30), 0),
                round(85 - (len(ranking_data) * 2 if ranking_data else 0), 0)  # Placeholder
            ],
            "benchmarks": [75, 70, 72, 70, 80]
        }

        # ==========================================
        # GRÁFICAS ADICIONALES CON DATOS REALES
        # ==========================================

        # 14. === marginCompareChart: Margen Bruto vs Neto por Tienda ===
        margin_compare_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.gross_margin,
            models.MonthlySummary.net_margin
        ).filter(
            models.MonthlySummary.period == current_period
        ).order_by(
            desc(models.MonthlySummary.gross_margin)
        ).limit(7).all()

        margin_compare_chart = {
            "labels": [m.store_name or "Tienda" for m in margin_compare_data],
            "gross_margin": [round(float(m.gross_margin or 0), 1) for m in margin_compare_data],
            "net_margin": [round(float(m.net_margin or 0), 1) for m in margin_compare_data]
        }

        # 15. === laborRatioChart: % Nómina sobre Ventas por Tienda ===
        labor_ratio_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.labor_cost,
            models.MonthlySummary.total_sales
        ).filter(
            models.MonthlySummary.period == current_period,
            models.MonthlySummary.total_sales > 0
        ).all()

        labor_ratios = []
        for lr in labor_ratio_data:
            ratio = (float(lr.labor_cost or 0) / float(lr.total_sales)) * 100 if lr.total_sales else 0
            labor_ratios.append({"name": lr.store_name or "Tienda", "ratio": round(ratio, 1)})

        labor_ratios.sort(key=lambda x: x["ratio"], reverse=True)
        labor_ratio_chart = {
            "labels": [l["name"] for l in labor_ratios[:7]],
            "values": [l["ratio"] for l in labor_ratios[:7]]
        }

        # 16. === fixedCostsChart: Desglose Costos Fijos ===
        fixed_costs_chart = {
            "labels": ["Nómina", "Renta", "Servicios"],
            "values": [total_labor, total_rent, total_utilities],
            "percentages": [
                round(total_labor / total_expenses * 100, 1) if total_expenses > 0 else 0,
                round(total_rent / total_expenses * 100, 1) if total_expenses > 0 else 0,
                round(total_utilities / total_expenses * 100, 1) if total_expenses > 0 else 0
            ]
        }

        # 17. === momVariationChart: Variación Mes a Mes por Tienda ===
        mom_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.sales_vs_previous,
            models.MonthlySummary.profit_vs_previous
        ).filter(
            models.MonthlySummary.period == current_period
        ).all()

        mom_variation_chart = {
            "labels": [m.store_name or "Tienda" for m in mom_data if m.sales_vs_previous is not None][:7],
            "sales_change": [round(float(m.sales_vs_previous or 0), 1) for m in mom_data if m.sales_vs_previous is not None][:7],
            "profit_change": [round(float(m.profit_vs_previous or 0), 1) for m in mom_data if m.profit_vs_previous is not None][:7]
        }

        # 18. === costStructureChart: Costo de Venta vs Gastos Operativos ===
        cost_structure_chart = {
            "labels": ["Costo de Venta", "Gastos Operativos"],
            "values": [total_cost_of_sales, total_expenses - total_cost_of_sales],
            "percentages": [
                round(total_cost_of_sales / total_sales * 100, 1) if total_sales > 0 else 0,
                round((total_expenses - total_cost_of_sales) / total_sales * 100, 1) if total_sales > 0 else 0
            ]
        }

        # 19. === marginEvolutionChart: Evolución de Márgenes por periodo ===
        margin_evolution = []
        for p in trend_periods:
            margins = db.query(
                func.avg(models.MonthlySummary.gross_margin).label('gross'),
                func.avg(models.MonthlySummary.net_margin).label('net')
            ).filter(
                models.MonthlySummary.period == p
            ).first()
            margin_evolution.append({
                "period": p,
                "gross": round(float(margins.gross or 0), 1),
                "net": round(float(margins.net or 0), 1)
            })

        margin_evolution_chart = {
            "labels": [m["period"] for m in margin_evolution],
            "gross_margin": [m["gross"] for m in margin_evolution],
            "net_margin": [m["net"] for m in margin_evolution]
        }

        # 20. === waterfallChart: Waterfall de P&L ===
        waterfall_chart = {
            "labels": ["Ventas", "Costo Venta", "Utilidad Bruta", "Gastos Op.", "Utilidad Neta"],
            "values": [
                total_sales,
                -total_cost_of_sales,
                total_sales - total_cost_of_sales,
                -(total_expenses - total_cost_of_sales),
                total_profit
            ],
            "colors": ["#34C759", "#FF3B30", "#34C759", "#FF3B30", total_profit >= 0 and "#34C759" or "#FF3B30"]
        }

        # 21. === scatterMarginChart: Ventas vs Margen (scatter) ===
        scatter_margin_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.total_sales,
            models.MonthlySummary.net_margin
        ).filter(
            models.MonthlySummary.period == current_period
        ).all()

        scatter_margin_chart = {
            "points": [
                {"x": float(s.total_sales or 0), "y": float(s.net_margin or 0), "label": s.store_name or ""}
                for s in scatter_margin_data
            ]
        }

        # 22. === rentRatioChart: % Renta sobre Ventas por Tienda ===
        rent_ratio_data = db.query(
            models.MonthlySummary.store_name,
            models.MonthlySummary.rent,
            models.MonthlySummary.total_sales
        ).filter(
            models.MonthlySummary.period == current_period,
            models.MonthlySummary.total_sales > 0
        ).all()

        rent_ratios = []
        for rr in rent_ratio_data:
            ratio = (float(rr.rent or 0) / float(rr.total_sales)) * 100 if rr.total_sales else 0
            rent_ratios.append({"name": rr.store_name or "Tienda", "ratio": round(ratio, 1)})

        rent_ratios.sort(key=lambda x: x["ratio"], reverse=True)
        rent_ratio_chart = {
            "labels": [r["name"] for r in rent_ratios[:7]],
            "values": [r["ratio"] for r in rent_ratios[:7]]
        }

        # 23. === Summary general ===
        summary = {
            "total_sales": total_sales,
            "total_expenses": total_expenses,
            "gross_profit": total_sales - total_cost_of_sales,
            "gross_margin": round(((total_sales - total_cost_of_sales) / total_sales * 100), 1) if total_sales > 0 else 0,
            "net_profit": total_profit,
            "net_margin": round(avg_margin, 1),
            "total_stores": len(store_data),
            "efficiency": round(efficiency_chart["value"], 1),
            "labor_ratio": round(total_labor / total_sales * 100, 1) if total_sales > 0 else 0,
            "rent_ratio": round(total_rent / total_sales * 100, 1) if total_sales > 0 else 0,
            "cost_of_sales_ratio": round(total_cost_of_sales / total_sales * 100, 1) if total_sales > 0 else 0
        }

        # 15. === Insights dinámicos ===
        top_expense_label = expense_labels[expense_values.index(max(expense_values))] if expense_values else "N/A"
        top_expense_pct = round(max(expense_values) / total_expense_sum * 100, 0) if total_expense_sum > 0 else 0

        insights = {
            "expense": f"<span class='text-pizza font-semibold'>{top_expense_label} {top_expense_pct}%</span> es el gasto principal. Considera optimizar recursos.",
            "efficiency": f"<span class='text-{'success' if efficiency_chart['value'] >= 75 else 'warning'} font-semibold'>{efficiency_chart['value']:.0f}% eficiencia</span> - {'Por encima del promedio de la industria (72%)' if efficiency_chart['value'] >= 72 else 'Por debajo del promedio de la industria (72%)'}. Objetivo: {efficiency_chart['target']}%.",
            "compare": f"<span class='text-success font-semibold'>Ventas {compare_chart['change_percent'][0]:+.1f}%</span>, gastos {compare_chart['change_percent'][1]:+.1f}%. {'Utilidad mejora.' if compare_chart['change_percent'][2] > 0 else 'Revisar costos.'}" if compare_chart else "Sin datos comparativos del periodo anterior.",
            "topGastos": f"<span class='text-warning font-semibold'>{' y '.join(expense_labels[:2])}</span> representan {sum(expense_dist_chart['values'][:2]):.0f}% del costo total.",
            "ranking": f"<span class='text-success font-semibold'>{ranking_chart['labels'][0]} lidera con {ranking_chart['margins'][0]:.0f}%</span> de margen." if ranking_chart['labels'] else "Sin datos de ranking.",
            "radar": f"<span class='text-success font-semibold'>{'Ventas y Margen fuertes' if radar_chart['values'][0] > 70 and radar_chart['values'][1] > 70 else 'Áreas de oportunidad identificadas'}.</span> {'Crecimiento bajo' if radar_chart['values'][3] < 50 else 'Buen crecimiento'} - enfocarse en mejora continua."
        }

        return {
            "success": True,
            "has_data": True,
            "generated_at": datetime.utcnow().isoformat(),
            "period": current_period,
            "available_periods": available_periods,
            "summary": summary,
            "charts": {
                "revenueChart": revenue_chart,
                "expenseChart": expense_chart,
                "trendChart": trend_chart,
                "correlationChart": correlation_chart,
                "expenseDistChart": expense_dist_chart,
                "efficiencyChart": efficiency_chart,
                "compareChart": compare_chart,
                "topCategoriesChart": top_categories_chart,
                "rankingChart": ranking_chart,
                "radarChart": radar_chart,
                # Nuevas gráficas
                "marginCompareChart": margin_compare_chart,
                "laborRatioChart": labor_ratio_chart,
                "fixedCostsChart": fixed_costs_chart,
                "momVariationChart": mom_variation_chart,
                "costStructureChart": cost_structure_chart,
                "marginEvolutionChart": margin_evolution_chart,
                "waterfallChart": waterfall_chart,
                "scatterMarginChart": scatter_margin_chart,
                "rentRatioChart": rent_ratio_chart
            },
            "insights": insights
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "has_data": False,
            "error": str(e)
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
