"""
CICLOPS - Modelos SQLAlchemy para PostgreSQL
Vault de datos financieros para Little Caesars
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Document(Base):
    """Documento subido (PDF, Excel, CSV)"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50))  # pdf, excel, csv
    store_id = Column(String(100), index=True)  # ID de sucursal
    store_name = Column(String(255))
    period = Column(String(50))  # Ej: "2024-01", "Enero 2024"
    rows_count = Column(Integer, default=0)
    columns = Column(JSON)  # Lista de columnas
    status = Column(String(50), default="uploaded")  # uploaded, processed, error
    uploaded_by = Column(String(255))  # UID de Firebase
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relaciones
    financial_records = relationship("FinancialRecord", back_populates="document")
    raw_data = relationship("RawDocumentData", back_populates="document", uselist=False)


class RawDocumentData(Base):
    """Datos raw del documento (para referencia)"""
    __tablename__ = "raw_document_data"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), unique=True)
    raw_text = Column(Text)  # Para PDFs
    raw_json = Column(JSON)  # Para Excel/CSV
    preview_data = Column(JSON)  # Primeras filas para preview

    document = relationship("Document", back_populates="raw_data")


class FinancialRecord(Base):
    """Registro financiero estructurado (del P&L)"""
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    store_id = Column(String(100), index=True)
    store_name = Column(String(255))
    period = Column(String(50), index=True)

    # Categoría del registro
    category = Column(String(100), index=True)  # ventas, costos, gastos, utilidad
    subcategory = Column(String(100))
    concept = Column(String(255))  # Descripción del concepto

    # Valores
    amount = Column(Float, default=0)
    percentage = Column(Float)  # % de ventas si aplica

    # Metadata
    row_number = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="financial_records")


class Store(Base):
    """Sucursal de Little Caesars"""
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(String(100), unique=True, index=True)
    name = Column(String(255))
    address = Column(String(500))
    zone = Column(String(100))  # Zona geográfica
    manager_uid = Column(String(255))  # UID del gerente en Firebase
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Analysis(Base):
    """Análisis generado por Julia AI"""
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    store_id = Column(String(100), index=True)
    analysis_type = Column(String(50))  # general, pl, expenses, comparison
    query = Column(Text)  # Pregunta del usuario
    result = Column(Text)  # Respuesta de Julia
    tokens_used = Column(Integer)
    user_uid = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MonthlySummary(Base):
    """Resumen mensual por sucursal (para queries rápidas)"""
    __tablename__ = "monthly_summaries"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(String(100), index=True)
    store_name = Column(String(255))
    period = Column(String(50), index=True)  # "2024-01"

    # Métricas principales
    total_sales = Column(Float, default=0)
    cost_of_sales = Column(Float, default=0)
    gross_profit = Column(Float, default=0)
    gross_margin = Column(Float)  # %

    operating_expenses = Column(Float, default=0)
    labor_cost = Column(Float, default=0)
    rent = Column(Float, default=0)
    utilities = Column(Float, default=0)

    net_profit = Column(Float, default=0)
    net_margin = Column(Float)  # %

    # Para comparativas
    sales_vs_previous = Column(Float)  # % cambio vs mes anterior
    profit_vs_previous = Column(Float)

    document_id = Column(Integer, ForeignKey("documents.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class User(Base):
    """Usuario del sistema"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255))
    role = Column(String(50), default="user")  # admin, user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
