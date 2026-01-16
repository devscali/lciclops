"""
Modelos Financieros - Little Caesars Reports
Julia: "La estructura de los datos financieros, todo bien categorizadito"
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Alert(BaseModel):
    type: str
    category: str
    message: str
    severity: AlertSeverity = AlertSeverity.WARNING


# === Revenue Models ===
class Revenue(BaseModel):
    in_store: float = Field(0, alias="ventas_mostrador")
    delivery: float = Field(0, alias="ventas_delivery")
    app: float = Field(0, alias="ventas_app")
    other: float = Field(0, alias="otros")
    total: float = 0

    def calculate_total(self):
        self.total = self.in_store + self.delivery + self.app + self.other
        return self.total


# === Cost Models ===
class IngredientCosts(BaseModel):
    flour: float = Field(0, alias="harina")
    cheese: float = Field(0, alias="queso")
    pepperoni: float = 0
    vegetables: float = Field(0, alias="vegetales")
    meats: float = Field(0, alias="carnes")
    beverages: float = Field(0, alias="bebidas")
    other: float = Field(0, alias="otros")
    total: float = 0

    def calculate_total(self):
        self.total = (
            self.flour + self.cheese + self.pepperoni +
            self.vegetables + self.meats + self.beverages + self.other
        )
        return self.total


class Costs(BaseModel):
    ingredients: IngredientCosts = IngredientCosts()
    total: float = 0

    def calculate_total(self):
        self.total = self.ingredients.calculate_total()
        return self.total


# === Expense Models ===
class Utilities(BaseModel):
    electricity: float = Field(0, alias="luz")
    water: float = Field(0, alias="agua")
    gas: float = 0
    total: float = 0

    def calculate_total(self):
        self.total = self.electricity + self.water + self.gas
        return self.total


class Expenses(BaseModel):
    labor: float = Field(0, alias="nomina")
    rent: float = Field(0, alias="renta")
    utilities: Utilities = Utilities()
    marketing: float = 0
    maintenance: float = Field(0, alias="mantenimiento")
    other: float = Field(0, alias="otros")
    total: float = 0

    def calculate_total(self):
        self.utilities.calculate_total()
        self.total = (
            self.labor + self.rent + self.utilities.total +
            self.marketing + self.maintenance + self.other
        )
        return self.total


# === Tax Models ===
class Taxes(BaseModel):
    vat: float = Field(0, alias="iva")
    income: float = Field(0, alias="isr")
    social: float = Field(0, alias="imss")
    total: float = 0

    def calculate_total(self):
        self.total = self.vat + self.income + self.social
        return self.total


# === Metrics Models ===
class FinancialMetrics(BaseModel):
    gross_profit: float = Field(0, alias="utilidad_bruta")
    gross_margin: float = Field(0, alias="margen_bruto")
    net_profit: float = Field(0, alias="utilidad_neta")
    net_margin: float = Field(0, alias="margen_neto")
    cog_percentage: float = Field(0, alias="costo_materia_prima_porcentaje")


class PeriodComparison(BaseModel):
    revenue_variation: str = Field("0%", alias="variacion_ingresos")
    expense_variation: str = Field("0%", alias="variacion_gastos")
    trend: str = "estable"  # estable, creciendo, decreciendo


# === Main Financial Data Model ===
class FinancialData(BaseModel):
    id: Optional[str] = None
    franchise_id: str
    document_id: Optional[str] = None
    period: str  # "2024-01"
    type: str = "monthly_summary"

    revenue: Revenue = Revenue()
    costs: Costs = Costs()
    expenses: Expenses = Expenses()
    taxes: Taxes = Taxes()

    metrics: FinancialMetrics = FinancialMetrics()
    alerts: List[Alert] = []
    comparison: Optional[PeriodComparison] = None

    created_at: Optional[datetime] = None

    def calculate_all(self):
        """Julia: Calcula todas las métricas automáticamente"""
        # Calcular totales
        self.revenue.calculate_total()
        self.costs.calculate_total()
        self.expenses.calculate_total()
        self.taxes.calculate_total()

        # Calcular métricas
        total_revenue = self.revenue.total
        if total_revenue > 0:
            gross_profit = total_revenue - self.costs.total
            net_profit = gross_profit - self.expenses.total - self.taxes.total

            self.metrics.gross_profit = gross_profit
            self.metrics.gross_margin = round(gross_profit / total_revenue, 4)
            self.metrics.net_profit = net_profit
            self.metrics.net_margin = round(net_profit / total_revenue, 4)
            self.metrics.cog_percentage = round(self.costs.total / total_revenue, 4)

        return self

    def generate_alerts(self, thresholds: Dict[str, float] = None):
        """Julia: Genera alertas basadas en umbrales"""
        if thresholds is None:
            thresholds = {
                "cog_percentage": 0.30,  # Costo de materia prima máximo 30%
                "labor_percentage": 0.25,  # Nómina máximo 25%
            }

        alerts = []
        total_revenue = self.revenue.total

        if total_revenue > 0:
            # Alerta de costo de materia prima
            if self.metrics.cog_percentage > thresholds["cog_percentage"]:
                alerts.append(Alert(
                    type="high_cost",
                    category="costs.ingredients",
                    message=f"Costo de materia prima al {self.metrics.cog_percentage:.1%}, "
                            f"arriba del objetivo ({thresholds['cog_percentage']:.0%})",
                    severity=AlertSeverity.WARNING
                ))

            # Alerta de nómina
            labor_pct = self.expenses.labor / total_revenue if total_revenue > 0 else 0
            if labor_pct > thresholds["labor_percentage"]:
                alerts.append(Alert(
                    type="high_expense",
                    category="expenses.labor",
                    message=f"Gasto de nómina al {labor_pct:.1%}, "
                            f"arriba del objetivo ({thresholds['labor_percentage']:.0%})",
                    severity=AlertSeverity.WARNING
                ))

        self.alerts = alerts
        return alerts


# === Response Models ===
class FinancialDataResponse(BaseModel):
    id: str
    period: str
    revenue: Revenue
    costs: Costs
    expenses: Expenses
    metrics: FinancialMetrics
    alerts: List[Alert]

    class Config:
        from_attributes = True


class DashboardData(BaseModel):
    current_period: str
    total_revenue: float
    net_margin: float
    revenue_trend: str  # "+15%", "-5%", etc.
    alerts: List[Alert]
    revenue_by_channel: Dict[str, float]
    expenses_breakdown: Dict[str, float]
