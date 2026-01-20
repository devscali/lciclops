"""
CICLOPS Backend - Producción con PostgreSQL
API para análisis financiero de Little Caesars
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from openai import OpenAI
import pandas as pd
import json
import os
from io import BytesIO
from dotenv import load_dotenv
from typing import Optional, List
import traceback
import pdfplumber

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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Cliente de OpenAI
openai_client = None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI API configurada")
else:
    print("⚠️ OPENAI_API_KEY no encontrada")


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
    return {
        "status": "healthy",
        "database": "connected",
        "openai": "connected" if openai_client else "disabled",
        "documents_count": doc_count
    }


# ============================================
# UPLOAD Y DOCUMENTOS
# ============================================

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


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Sube un archivo y retorna preview para confirmación"""
    try:
        filename = file.filename.lower()
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

                data = df.to_dict(orient='records')
                columns = list(df.columns)

                # Analizar campos con AI
                ai_analysis = await analyze_fields_with_ai(data, columns, f"{file.filename} - {sheet_name}")

                # Crear documento en DB
                doc = models.Document(
                    filename=f"{file.filename}" if len(sheets_data) == 1 else f"{file.filename} [{sheet_name}]",
                    file_type="excel" if not filename.endswith('.csv') else "csv",
                    rows_count=len(df),
                    columns=columns,
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
    db: Session = Depends(get_db)
):
    """Confirma un documento y lo guarda en el vault"""
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
    limit: int = 50
):
    """Lista documentos del vault"""
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
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Obtiene detalles de un documento"""
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
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Elimina un documento del vault"""
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
# ANÁLISIS CON OPENAI
# ============================================

@app.post("/analyze/{doc_id}")
async def analyze_document(
    doc_id: int,
    analysis_type: str = "general",
    db: Session = Depends(get_db)
):
    """Analiza un documento con OpenAI GPT-4"""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API no configurada")

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

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[
                {"role": "system", "content": "Eres Julia, experta en análisis financiero para restaurantes Little Caesars. Respondes en español de manera profesional."},
                {"role": "user", "content": prompt}
            ]
        )

        # Guardar análisis en DB
        analysis = models.Analysis(
            document_id=doc_id,
            store_id=doc.store_id,
            analysis_type=analysis_type,
            query=f"Análisis {analysis_type}",
            result=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens
        )
        db.add(analysis)
        db.commit()

        return {
            "success": True,
            "analysis": {
                "doc_id": doc_id,
                "filename": doc.filename,
                "type": analysis_type,
                "result": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens
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
    db: Session = Depends(get_db)
):
    """Chat con Julia - consultas en lenguaje natural"""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API no configurada")

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

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1500,
            temperature=0.7,
            messages=messages
        )

        # Guardar en análisis
        analysis = models.Analysis(
            store_id=request.store_id,
            analysis_type="chat",
            query=request.message,
            result=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens
        )
        db.add(analysis)
        db.commit()

        return {
            "success": True,
            "response": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# VAULT - Resumen y Queries
# ============================================

@app.get("/vault/summary")
async def get_vault_summary(db: Session = Depends(get_db)):
    """Resumen del vault"""
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
async def get_stores(db: Session = Depends(get_db)):
    """Lista sucursales con datos"""
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
    limit: int = 20
):
    """Lista análisis realizados"""
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
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Estadísticas para el dashboard principal"""

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
# STATIC FILES - Servir frontend HTML
# ============================================

# Ruta al directorio de archivos estáticos (root del proyecto)
import pathlib
STATIC_DIR = pathlib.Path(__file__).parent.parent

# Servir archivos estáticos (CSS, JS, images si los hay)
# app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Servir index.html en la raíz
@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

# Servir cualquier archivo HTML
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
