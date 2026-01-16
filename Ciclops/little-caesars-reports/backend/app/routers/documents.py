"""
Documents Router - Little Caesars Reports
Julia: "Aquí suben los PDFs y yo los proceso"
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from typing import Optional, List
import uuid
from datetime import datetime

from app.models import (
    DocumentType, DocumentStatus, DocumentResponse,
    DocumentListResponse, DocumentInDB
)
from app.services import (
    get_firebase_service, FirebaseService,
    get_pdf_service, PDFService,
    get_claude_service, ClaudeService
)
from app.routers.auth import get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: Optional[DocumentType] = None,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service),
    pdf_service: PDFService = Depends(get_pdf_service),
    claude_service: ClaudeService = Depends(get_claude_service)
):
    """
    Subir y procesar un documento
    Julia: "¡Órale! Me llegó un documento nuevo para analizar"
    """
    # Validar tipo de archivo
    allowed_types = ["application/pdf", "image/png", "image/jpeg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no soportado. Usa: {', '.join(allowed_types)}"
        )

    try:
        # Leer contenido del archivo
        file_content = await file.read()

        # Generar ID único
        doc_id = str(uuid.uuid4())
        franchise_id = current_user.get("franchise_id", "default")

        # Subir archivo a Storage
        file_path = f"documents/{franchise_id}/{doc_id}/{file.filename}"
        file_url = await firebase.upload_file(
            file_content,
            file_path,
            content_type=file.content_type
        )

        # Crear documento inicial en Firestore
        doc_data = {
            "user_id": current_user["uid"],
            "franchise_id": franchise_id,
            "type": document_type.value if document_type else DocumentType.OTHER.value,
            "file_name": file.filename,
            "file_url": file_url,
            "uploaded_at": datetime.utcnow(),
            "status": DocumentStatus.PROCESSING.value,
        }

        await firebase.create_document("documents", doc_data, doc_id=doc_id)

        # Procesar documento (extraer texto)
        try:
            if file.content_type == "application/pdf":
                extraction_result = await pdf_service.extract_text_from_pdf(file_content)
            else:
                extraction_result = await pdf_service.extract_from_image(file_content)

            # Identificar tipo de documento si no se especificó
            if not document_type:
                detected_type = pdf_service.identify_document_type(extraction_result["text"])
                doc_data["type"] = detected_type

            # Analizar con Claude
            analysis_result = await claude_service.analyze_financial_document(
                extracted_text=extraction_result["text"],
                document_type=doc_data["type"],
                tables=extraction_result.get("tables", [])
            )

            # Actualizar documento con resultados
            update_data = {
                "status": DocumentStatus.COMPLETED.value,
                "processed_at": datetime.utcnow(),
                "extracted_data": analysis_result,
                "confidence": extraction_result.get("confidence", 0),
                "type": analysis_result.get("tipo_documento", doc_data["type"]),
            }

            # Extraer periodo si está disponible
            if analysis_result.get("periodo"):
                update_data["period"] = {
                    "start": analysis_result.get("fecha_documento", datetime.utcnow().isoformat()),
                    "end": analysis_result.get("fecha_documento", datetime.utcnow().isoformat())
                }

            await firebase.update_document("documents", doc_id, update_data)

            # Guardar datos financieros estructurados
            if analysis_result.get("datos"):
                financial_doc = {
                    "franchise_id": franchise_id,
                    "document_id": doc_id,
                    "period": analysis_result.get("periodo", datetime.utcnow().strftime("%Y-%m")),
                    "type": "document_extraction",
                    "data": analysis_result.get("datos"),
                    "alerts": analysis_result.get("alertas", [])
                }
                await firebase.create_document("financial_data", financial_doc)

            return {
                "id": doc_id,
                "type": update_data["type"],
                "file_name": file.filename,
                "status": DocumentStatus.COMPLETED,
                "uploaded_at": doc_data["uploaded_at"],
                "processed_at": update_data["processed_at"],
                "confidence": update_data["confidence"],
                "period": update_data.get("period")
            }

        except Exception as processing_error:
            # Marcar como fallido si hay error en procesamiento
            await firebase.update_document("documents", doc_id, {
                "status": DocumentStatus.FAILED.value,
                "error_message": str(processing_error)
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error procesando documento: {str(processing_error)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error subiendo documento: {str(e)}"
        )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[DocumentStatus] = None,
    type_filter: Optional[DocumentType] = None,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Listar documentos del usuario
    """
    try:
        franchise_id = current_user.get("franchise_id", "default")

        filters = [("franchise_id", "==", franchise_id)]

        if status_filter:
            filters.append(("status", "==", status_filter.value))
        if type_filter:
            filters.append(("type", "==", type_filter.value))

        documents = await firebase.query_documents(
            "documents",
            filters=filters,
            order_by="uploaded_at",
            order_direction="DESCENDING",
            limit=page_size
        )

        return {
            "documents": documents,
            "total": len(documents),
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Obtener un documento específico con sus datos extraídos
    """
    try:
        document = await firebase.get_document("documents", document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado"
            )

        # Verificar que pertenece a la franquicia del usuario
        franchise_id = current_user.get("franchise_id", "default")
        if document.get("franchise_id") != franchise_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este documento"
            )

        return document

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Eliminar un documento
    """
    try:
        document = await firebase.get_document("documents", document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado"
            )

        franchise_id = current_user.get("franchise_id", "default")
        if document.get("franchise_id") != franchise_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este documento"
            )

        # Eliminar archivo de Storage
        if document.get("file_url"):
            file_path = f"documents/{franchise_id}/{document_id}/{document['file_name']}"
            try:
                await firebase.delete_file(file_path)
            except Exception:
                pass  # Continuar aunque no se pueda eliminar el archivo

        # Eliminar documento de Firestore
        await firebase.delete_document("documents", document_id)

        return {"message": "Documento eliminado correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service),
    pdf_service: PDFService = Depends(get_pdf_service),
    claude_service: ClaudeService = Depends(get_claude_service)
):
    """
    Reprocesar un documento
    Julia: "Si algo salió mal la primera vez, lo vuelvo a intentar"
    """
    try:
        document = await firebase.get_document("documents", document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado"
            )

        # Descargar archivo
        franchise_id = current_user.get("franchise_id", "default")
        file_path = f"documents/{franchise_id}/{document_id}/{document['file_name']}"
        file_content = await firebase.download_file(file_path)

        # Marcar como procesando
        await firebase.update_document("documents", document_id, {
            "status": DocumentStatus.PROCESSING.value
        })

        # Reprocesar
        extraction_result = await pdf_service.extract_text_from_pdf(file_content)
        analysis_result = await claude_service.analyze_financial_document(
            extracted_text=extraction_result["text"],
            document_type=document.get("type"),
            tables=extraction_result.get("tables", [])
        )

        # Actualizar
        await firebase.update_document("documents", document_id, {
            "status": DocumentStatus.COMPLETED.value,
            "processed_at": datetime.utcnow(),
            "extracted_data": analysis_result,
            "confidence": extraction_result.get("confidence", 0)
        })

        return {"message": "Documento reprocesado correctamente"}

    except Exception as e:
        await firebase.update_document("documents", document_id, {
            "status": DocumentStatus.FAILED.value,
            "error_message": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
