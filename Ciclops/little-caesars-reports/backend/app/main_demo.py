"""
CICLOPS Backend - Modo Demo
Funciona sin Firebase, solo con OpenAI API para análisis
Soporta: Excel, CSV, PDF
Incluye: Chat con Julia, Vault de datos
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel
import pandas as pd
import json
import os
from io import BytesIO
from dotenv import load_dotenv
from typing import Optional, List, Dict
import traceback
import pdfplumber

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="CICLOPS API - Demo Mode",
    description="API para análisis financiero de Little Caesars con Julia AI",
    version="2.0.0"
)


# Modelos Pydantic
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    history: Optional[List[Dict[str, str]]] = []

# CORS - permitir frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # No puede ser True con origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Cliente de OpenAI
openai_client = None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI API configurada correctamente")
else:
    print("⚠️ OPENAI_API_KEY no encontrada - análisis IA deshabilitado")

# Almacenamiento en memoria (demo)
documents_store = []
analysis_store = []


@app.get("/")
async def root():
    return {
        "message": "🍕 CICLOPS API - Modo Demo",
        "status": "running",
        "openai_enabled": openai_client is not None,
        "endpoints": {
            "upload": "POST /upload",
            "analyze": "POST /analyze",
            "documents": "GET /documents",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "mode": "demo",
        "openai": "connected" if openai_client else "disabled",
        "documents_count": len(documents_store)
    }


def extract_text_from_pdf(content: bytes) -> str:
    """Extrae texto de un PDF usando pdfplumber"""
    text_content = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            # Intentar extraer tablas primero
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if row:
                            text_content.append(" | ".join([str(cell) if cell else "" for cell in row]))
            else:
                # Si no hay tablas, extraer texto normal
                text = page.extract_text()
                if text:
                    text_content.append(text)
    return "\n".join(text_content)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Sube un archivo Excel/CSV/PDF y extrae los datos
    """
    try:
        # Validar tipo de archivo
        filename = file.filename.lower()
        allowed_extensions = ['.xlsx', '.xls', '.csv', '.pdf']
        if not any(filename.endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail="Solo se permiten archivos Excel (.xlsx, .xls), CSV (.csv) o PDF (.pdf)"
            )

        # Leer contenido
        content = await file.read()

        # Parsear según tipo
        is_pdf = filename.endswith('.pdf')

        if is_pdf:
            # Extraer texto del PDF
            pdf_text = extract_text_from_pdf(content)

            # Crear un "dataframe" simple con el contenido
            lines = [line.strip() for line in pdf_text.split('\n') if line.strip()]
            df = pd.DataFrame({"contenido": lines})
            data = df.to_dict(orient='records')

            doc_info = {
                "id": len(documents_store) + 1,
                "filename": file.filename,
                "type": "pdf",
                "rows": len(lines),
                "columns": ["contenido"],
                "preview": lines[:10],
                "full_text": pdf_text[:5000],  # Primeros 5000 chars para preview
                "status": "uploaded"
            }

            documents_store.append({
                "info": doc_info,
                "data": data,
                "df_json": df.to_json(),
                "raw_text": pdf_text
            })
        else:
            # Excel o CSV
            if filename.endswith('.csv'):
                df = pd.read_csv(BytesIO(content))
            else:
                df = pd.read_excel(BytesIO(content))

            data = df.to_dict(orient='records')

            doc_info = {
                "id": len(documents_store) + 1,
                "filename": file.filename,
                "type": "excel" if not filename.endswith('.csv') else "csv",
                "rows": len(df),
                "columns": list(df.columns),
                "preview": data[:5],
                "status": "uploaded"
            }

            documents_store.append({
                "info": doc_info,
                "data": data,
                "df_json": df.to_json()
            })

        return {
            "success": True,
            "message": f"Archivo '{file.filename}' subido correctamente",
            "document": doc_info
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/{doc_id}")
async def analyze_document(doc_id: int, analysis_type: str = "general"):
    """
    Analiza un documento con OpenAI GPT-4
    """
    if not openai_client:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API no configurada. Agrega OPENAI_API_KEY al .env"
        )

    # Buscar documento
    doc = None
    for d in documents_store:
        if d["info"]["id"] == doc_id:
            doc = d
            break

    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento {doc_id} no encontrado")

    try:
        # Preparar datos según tipo de documento
        is_pdf = doc["info"].get("type") == "pdf"

        if is_pdf:
            # Para PDFs, usar el texto raw
            raw_text = doc.get("raw_text", "")
            data_summary = f"""
            Archivo: {doc['info']['filename']}
            Tipo: PDF (Estado de Resultados)

            Contenido del documento:
            {raw_text[:8000]}
            """
        else:
            # Para Excel/CSV
            df = pd.read_json(doc["df_json"])
            data_summary = f"""
            Archivo: {doc['info']['filename']}
            Filas: {len(df)}
            Columnas: {', '.join(df.columns.tolist())}

            Primeras filas:
            {df.head(10).to_string()}

            Estadísticas:
            {df.describe().to_string()}
            """

        # Prompt según tipo de análisis
        prompts = {
            "general": f"""
            Analiza estos datos financieros de un restaurante Little Caesars:

            {data_summary}

            Proporciona:
            1. Resumen ejecutivo (2-3 oraciones)
            2. Métricas clave identificadas
            3. Tendencias o patrones notables
            4. Alertas o áreas de preocupación
            5. Recomendaciones

            Responde en español y en formato estructurado.
            """,

            "pl": f"""
            Analiza este estado de resultados (P&L) de Little Caesars:

            {data_summary}

            Calcula y proporciona:
            1. Ventas totales
            2. Costo de ventas y margen bruto
            3. Gastos operativos desglosados
            4. Utilidad neta y margen neto
            5. Comparativa vs mes anterior si hay datos
            6. Alertas sobre gastos excesivos

            Responde en español con números formateados en pesos mexicanos.
            """,

            "expenses": f"""
            Analiza los gastos de este restaurante Little Caesars:

            {data_summary}

            Identifica:
            1. Top 5 categorías de gasto
            2. Gastos que exceden benchmarks de la industria
            3. Oportunidades de ahorro
            4. Tendencias preocupantes

            Responde en español.
            """
        }

        prompt = prompts.get(analysis_type, prompts["general"])

        # Llamar a OpenAI GPT-4
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[
                {"role": "system", "content": "Eres Julia, una asistente experta en análisis financiero para restaurantes Little Caesars. Respondes siempre en español de manera clara y profesional."},
                {"role": "user", "content": prompt}
            ]
        )

        analysis_result = {
            "doc_id": doc_id,
            "filename": doc["info"]["filename"],
            "analysis_type": analysis_type,
            "result": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens
        }

        analysis_store.append(analysis_result)

        return {
            "success": True,
            "analysis": analysis_result
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents():
    """Lista todos los documentos subidos"""
    return {
        "count": len(documents_store),
        "documents": [d["info"] for d in documents_store]
    }


@app.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    """Obtiene detalles de un documento"""
    for d in documents_store:
        if d["info"]["id"] == doc_id:
            return d["info"]
    raise HTTPException(status_code=404, detail="Documento no encontrado")


@app.get("/analyses")
async def list_analyses():
    """Lista todos los análisis realizados"""
    return {
        "count": len(analysis_store),
        "analyses": analysis_store
    }


# ============================================
# CHAT CON JULIA - Consultas en lenguaje natural
# ============================================

@app.post("/chat")
async def chat_with_julia(request: ChatRequest):
    """
    Chat con Julia - Asistente financiera IA
    Responde preguntas sobre los datos del vault
    """
    if not openai_client:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API no configurada. Agrega OPENAI_API_KEY al .env"
        )

    try:
        # Construir contexto con datos disponibles
        data_context = request.context or ""

        # Agregar resumen de documentos en memoria
        if documents_store:
            data_context += "\n\nDocumentos cargados en esta sesion:\n"
            for doc in documents_store:
                info = doc["info"]
                data_context += f"- {info['filename']}: {info['rows']} filas, tipo: {info['type']}\n"

                # Incluir datos de preview para contexto
                if info['type'] == 'pdf':
                    raw_text = doc.get('raw_text', '')[:3000]
                    data_context += f"  Contenido:\n{raw_text}\n"
                else:
                    preview = doc.get('data', [])[:10]
                    if preview:
                        data_context += f"  Columnas: {', '.join(info['columns'])}\n"
                        data_context += f"  Muestra de datos: {json.dumps(preview[:5], ensure_ascii=False)}\n"

        # Construir mensajes para el chat
        messages = [
            {
                "role": "system",
                "content": f"""Eres Julia, una asistente experta en análisis financiero para restaurantes Little Caesars en Mexico.

Tu personalidad:
- Profesional pero amigable
- Respondes siempre en español
- Das respuestas claras y accionables
- Cuando muestras numeros, los formateas en pesos mexicanos
- Cuando detectas problemas, sugieres soluciones

Capacidades:
- Analizar estados de resultados (P&L)
- Comparar rendimiento entre sucursales
- Identificar tendencias y anomalias
- Calcular metricas financieras
- Dar recomendaciones basadas en datos

Datos disponibles:
{data_context}

Si no tienes datos suficientes para responder, sugieres amablemente que el usuario suba los documentos necesarios.
Cuando hagas calculos, muestra tu trabajo brevemente.
Usa emojis con moderacion para hacer las respuestas mas amigables.
"""
            }
        ]

        # Agregar historial de conversacion
        for msg in (request.history or [])[-6:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # Agregar mensaje actual
        messages.append({
            "role": "user",
            "content": request.message
        })

        # Llamar a OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1500,
            temperature=0.7,
            messages=messages
        )

        return {
            "success": True,
            "response": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vault/summary")
async def get_vault_summary():
    """
    Resumen de todos los datos en el vault (memoria)
    """
    summary = {
        "total_documents": len(documents_store),
        "documents": [],
        "total_rows": 0,
        "types": {"pdf": 0, "excel": 0, "csv": 0}
    }

    for doc in documents_store:
        info = doc["info"]
        summary["documents"].append({
            "id": info["id"],
            "filename": info["filename"],
            "type": info["type"],
            "rows": info["rows"],
            "status": info.get("status", "uploaded")
        })
        summary["total_rows"] += info["rows"]
        doc_type = info["type"]
        if doc_type in summary["types"]:
            summary["types"][doc_type] += 1

    return summary


@app.post("/vault/query")
async def query_vault(query: str):
    """
    Consulta especifica al vault
    """
    # Por ahora retorna datos raw, despues se puede hacer mas inteligente
    results = []
    query_lower = query.lower()

    for doc in documents_store:
        info = doc["info"]
        # Busqueda simple por nombre
        if query_lower in info["filename"].lower():
            results.append({
                "document": info,
                "data_preview": doc.get("data", [])[:20]
            })

    return {
        "query": query,
        "results_count": len(results),
        "results": results
    }


# Para correr: python -m uvicorn app.main_demo:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
