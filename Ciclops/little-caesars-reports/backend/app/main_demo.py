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


async def analyze_fields_with_ai(data_preview: list, columns: list, filename: str) -> dict:
    """Usa AI para detectar y mapear campos automáticamente"""
    if not openai_client:
        return {"detected_fields": {}, "data_type": "unknown", "summary": "AI no disponible", "recommended_category": "general"}

    try:
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


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), skip_ai: bool = False):
    """
    Sube un archivo Excel/CSV/PDF y extrae los datos
    - skip_ai: Si True, no ejecuta análisis AI (más rápido para archivos grandes)
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
        file_size_mb = len(content) / (1024 * 1024)
        print(f"📁 Procesando archivo: {file.filename} ({file_size_mb:.2f} MB)")

        # Auto-skip AI para archivos grandes (> 5MB)
        if file_size_mb > 5:
            print(f"⚠️ Archivo grande detectado, desactivando AI analysis")
            skip_ai = True

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
                "full_text": pdf_text[:5000],
                "status": "uploaded"
            }

            documents_store.append({
                "info": doc_info,
                "data": data,
                "df_json": df.to_json(),
                "raw_text": pdf_text
            })

            return {
                "success": True,
                "message": f"PDF '{file.filename}' procesado",
                "sheets_count": 1,
                "documents": [doc_info]
            }
        else:
            # Excel o CSV
            if filename.endswith('.csv'):
                df = pd.read_csv(BytesIO(content))
                sheets_data = {"Datos": df}
            else:
                # Excel: leer TODAS las hojas
                print(f"📊 Leyendo hojas del Excel...")
                excel_file = pd.ExcelFile(BytesIO(content))
                sheet_names = excel_file.sheet_names
                print(f"📋 Hojas encontradas: {len(sheet_names)} - {sheet_names[:5]}{'...' if len(sheet_names) > 5 else ''}")

                sheets_data = {}
                for sheet_name in sheet_names:
                    try:
                        df = pd.read_excel(excel_file, sheet_name=sheet_name)
                        if not df.empty and len(df.columns) > 0:
                            sheets_data[sheet_name] = df
                    except Exception as e:
                        print(f"⚠️ Error leyendo hoja '{sheet_name}': {e}")
                        continue

            # Procesar cada hoja
            documents_created = []
            total_sheets = len(sheets_data)

            # Limitar AI analysis a máximo 3 hojas para evitar timeout
            max_ai_sheets = 3 if not skip_ai else 0
            ai_processed = 0

            for idx, (sheet_name, df) in enumerate(sheets_data.items()):
                print(f"  → Procesando hoja {idx+1}/{total_sheets}: {sheet_name}")

                df.columns = [str(col).strip() for col in df.columns]
                df = df.dropna(how='all')

                if df.empty:
                    continue

                data = df.to_dict(orient='records')
                columns = list(df.columns)

                # Solo analizar con AI las primeras N hojas para evitar timeout
                ai_analysis = None
                if not skip_ai and ai_processed < max_ai_sheets and len(df) < 10000:
                    try:
                        print(f"    🤖 Analizando con AI...")
                        ai_analysis = await analyze_fields_with_ai(data, columns, f"{file.filename} - {sheet_name}")
                        ai_processed += 1
                    except Exception as e:
                        print(f"    ⚠️ AI analysis failed: {e}")
                        ai_analysis = None

                doc_info = {
                    "id": len(documents_store) + 1,
                    "filename": f"{file.filename}" if total_sheets == 1 else f"{file.filename} [{sheet_name}]",
                    "sheet_name": sheet_name,
                    "type": "excel" if not filename.endswith('.csv') else "csv",
                    "rows": len(df),
                    "columns": columns,
                    "preview": data[:5],
                    "ai_analysis": ai_analysis,
                    "status": "uploaded"
                }

                documents_store.append({
                    "info": doc_info,
                    "data": data,
                    "df_json": df.to_json()
                })

                documents_created.append(doc_info)

            if not documents_created:
                raise HTTPException(status_code=400, detail="No se encontraron datos válidos en el archivo")

            print(f"✅ Procesado: {len(documents_created)} hojas, {ai_processed} con AI")

            return {
                "success": True,
                "message": f"Archivo '{file.filename}' procesado - {len(documents_created)} hoja(s)",
                "sheets_count": len(documents_created),
                "ai_analyzed": ai_processed,
                "documents": documents_created
            }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/analyze/{doc_id}")
async def analyze_document_fields(doc_id: int):
    """
    Analiza campos de un documento con AI (para docs que se subieron sin AI)
    """
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API no configurada")

    # Buscar documento
    doc = None
    for d in documents_store:
        if d["info"]["id"] == doc_id:
            doc = d
            break

    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento {doc_id} no encontrado")

    if doc["info"].get("type") == "pdf":
        return {"success": True, "message": "PDFs no requieren análisis de campos", "ai_analysis": None}

    try:
        data = doc.get("data", [])
        columns = doc["info"].get("columns", [])
        filename = doc["info"]["filename"]

        ai_analysis = await analyze_fields_with_ai(data, columns, filename)

        # Actualizar el documento
        doc["info"]["ai_analysis"] = ai_analysis

        return {
            "success": True,
            "doc_id": doc_id,
            "ai_analysis": ai_analysis
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
