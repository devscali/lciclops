"""
Modelos de Documento - Little Caesars Reports
Julia: "Aquí definimos la estructura de los documentos que proceso"
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


class DocumentType(str, Enum):
    INVOICE = "invoice"
    BANK_STATEMENT = "bank_statement"
    SALES_REPORT = "sales_report"
    INVENTORY = "inventory"
    OTHER = "other"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentPeriod(BaseModel):
    start: date
    end: date


class DocumentUpload(BaseModel):
    file_name: str
    document_type: Optional[DocumentType] = None


class DocumentInDB(BaseModel):
    id: str
    user_id: str
    franchise_id: str
    type: DocumentType
    file_name: str
    file_url: str
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    status: DocumentStatus = DocumentStatus.PENDING
    extracted_data: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    period: Optional[DocumentPeriod] = None
    error_message: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    type: DocumentType
    file_name: str
    status: DocumentStatus
    uploaded_at: datetime
    processed_at: Optional[datetime]
    confidence: Optional[float]
    period: Optional[DocumentPeriod]

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
