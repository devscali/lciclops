"""
CICLOPS Backend - Modo Demo
Funciona sin Firebase, solo con Claude API para análisis
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import anthropic
import pandas as pd
import json
import os
from io import BytesIO
from dotenv import load_dotenv
from typing import Optional
import traceback

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="CICLOPS API - Demo Mode",
    description="API para análisis financiero de Little Caesars",
    version="1.0.0-demo"
)

# CORS - permitir frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir esto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente de Anthropic
anthropic_client = None
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if ANTHROPIC_API_KEY:
    anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("✅ Anthropic API configurada correctamente")
else:
    print("⚠️ ANTHROPIC_API_KEY no encontrada - análisis IA deshabilitado")

# Almacenamiento en memoria (demo)
documents_store = []
analysis_store = []


@app.get("/")
async def root():
    return {
        "message": "🍕 CICLOPS API - Modo Demo",
        "status": "running",
        "anthropic_enabled": anthropic_client is not None,
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
        "anthropic": "connected" if anthropic_client else "disabled",
        "documents_count": len(documents_store)
    }


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Sube un archivo Excel/CSV y extrae los datos
    """
    try:
        # Validar tipo de archivo
        filename = file.filename.lower()
        if not any(filename.endswith(ext) for ext in ['.xlsx', '.xls', '.csv']):
            raise HTTPException(
                status_code=400,
                detail="Solo se permiten archivos Excel (.xlsx, .xls) o CSV (.csv)"
            )

        # Leer contenido
        content = await file.read()

        # Parsear según tipo
        if filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))

        # Convertir a diccionario
        data = df.to_dict(orient='records')

        # Info del archivo
        doc_info = {
            "id": len(documents_store) + 1,
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "preview": data[:5],  # Primeras 5 filas
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
    Analiza un documento con Claude AI
    """
    if not anthropic_client:
        raise HTTPException(
            status_code=503,
            detail="Anthropic API no configurada. Agrega ANTHROPIC_API_KEY al .env"
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
        # Preparar datos para Claude
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

        # Llamar a Claude
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        analysis_result = {
            "doc_id": doc_id,
            "filename": doc["info"]["filename"],
            "analysis_type": analysis_type,
            "result": message.content[0].text,
            "tokens_used": message.usage.input_tokens + message.usage.output_tokens
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


# Servir archivos estáticos del frontend
# Los archivos HTML están en la raíz del repo (../../)
STATIC_DIR = Path(__file__).parent.parent.parent.parent  # Sube a lciclops/
if STATIC_DIR.exists():
    # Servir index.html en la raíz
    @app.get("/app")
    @app.get("/app/")
    async def serve_app():
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "index.html not found"}

    # Servir otros archivos HTML
    @app.get("/app/{filename}")
    async def serve_html(filename: str):
        file_path = STATIC_DIR / filename
        if file_path.exists() and file_path.suffix in ['.html', '.css', '.js', '.png', '.jpg', '.svg', '.ico']:
            return FileResponse(file_path)
        return {"error": f"{filename} not found"}


# Para correr: python -m uvicorn app.main_demo:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
