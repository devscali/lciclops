"""
CICLOPS - Schemas Pydantic para validación de datos
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================
# Document Schemas
# ============================================

class DocumentBase(BaseModel):
    filename: str
    file_type: Optional[str] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    period: Optional[str] = None


class DocumentCreate(DocumentBase):
    rows_count: int = 0
    columns: Optional[List[str]] = []
    uploaded_by: Optional[str] = None


class DocumentResponse(DocumentBase):
    id: int
    rows_count: int
    columns: Optional[List[str]]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentWithPreview(DocumentResponse):
    preview: Optional[List[Dict[str, Any]]] = []
    raw_text: Optional[str] = None


# ============================================
# Financial Record Schemas
# ============================================

class FinancialRecordBase(BaseModel):
    store_id: str
    store_name: Optional[str] = None
    period: str
    category: str
    subcategory: Optional[str] = None
    concept: str
    amount: float = 0
    percentage: Optional[float] = None


class FinancialRecordCreate(FinancialRecordBase):
    document_id: int
    row_number: Optional[int] = None


class FinancialRecordResponse(FinancialRecordBase):
    id: int
    document_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Monthly Summary Schemas
# ============================================

class MonthlySummaryBase(BaseModel):
    store_id: str
    store_name: Optional[str] = None
    period: str
    total_sales: float = 0
    cost_of_sales: float = 0
    gross_profit: float = 0
    gross_margin: Optional[float] = None
    operating_expenses: float = 0
    labor_cost: float = 0
    rent: float = 0
    utilities: float = 0
    net_profit: float = 0
    net_margin: Optional[float] = None


class MonthlySummaryCreate(MonthlySummaryBase):
    document_id: Optional[int] = None
    sales_vs_previous: Optional[float] = None
    profit_vs_previous: Optional[float] = None


class MonthlySummaryResponse(MonthlySummaryBase):
    id: int
    sales_vs_previous: Optional[float]
    profit_vs_previous: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Store Schemas
# ============================================

class StoreBase(BaseModel):
    store_id: str
    name: str
    address: Optional[str] = None
    zone: Optional[str] = None


class StoreCreate(StoreBase):
    manager_uid: Optional[str] = None


class StoreResponse(StoreBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Analysis Schemas
# ============================================

class AnalysisCreate(BaseModel):
    document_id: Optional[int] = None
    store_id: Optional[str] = None
    analysis_type: str
    query: str
    result: str
    tokens_used: int = 0
    user_uid: Optional[str] = None


class AnalysisResponse(AnalysisCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# Chat Schemas
# ============================================

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    history: Optional[List[Dict[str, str]]] = []
    store_id: Optional[str] = None  # Filtrar por sucursal


class ChatResponse(BaseModel):
    success: bool
    response: str
    tokens_used: int


# ============================================
# Vault Schemas
# ============================================

class VaultSummary(BaseModel):
    total_documents: int
    total_stores: int
    total_records: int
    documents_by_type: Dict[str, int]
    recent_documents: List[DocumentResponse]


class VaultQuery(BaseModel):
    query: str
    store_id: Optional[str] = None
    period: Optional[str] = None
    limit: int = 100


# ============================================
# Upload Confirm Schema
# ============================================

class UploadConfirm(BaseModel):
    doc_id: int
    store_id: str
    store_name: str
    period: str
    confirm: bool = True
    user_uid: Optional[str] = None
