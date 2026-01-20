"""
Claude AI Service - Little Caesars Reports
Julia: "Aquí es donde Claude me ayuda a interpretar los datos financieros"
"""
import json
import logging
from typing import Dict, Any, Optional
from anthropic import Anthropic

from app.config import get_settings
from app.models import FinancialData, DocumentType

logger = logging.getLogger(__name__)
settings = get_settings()


FINANCIAL_EXTRACTION_PROMPT = """Eres Julia, una data scientist experta en finanzas de restaurantes (Little Caesars).
Tu trabajo es analizar texto extraído de documentos financieros y estructurar los datos.

IMPORTANTE:
- Identifica TODOS los números relevantes
- Clasifícalos correctamente en las categorías
- Si no encuentras un valor, usa 0
- Detecta anomalías o datos que no cuadran
- Responde SIEMPRE en JSON válido

Categorías para Little Caesars:

INGRESOS (revenue):
- ventas_mostrador: Ventas en tienda/mostrador
- ventas_delivery: Ventas por entrega a domicilio
- ventas_app: Ventas por aplicación
- otros: Otros ingresos

COSTOS (costs) - Materia Prima:
- harina: Harina para masa
- queso: Queso mozzarella y otros
- pepperoni: Pepperoni y embutidos
- vegetales: Verduras y vegetales
- carnes: Carnes (excepto pepperoni)
- bebidas: Refrescos, aguas
- otros: Otros ingredientes

GASTOS (expenses):
- nomina: Sueldos y salarios
- renta: Renta del local
- luz: Electricidad
- agua: Agua
- gas: Gas
- marketing: Publicidad y promociones
- mantenimiento: Reparaciones y mantenimiento
- otros: Otros gastos

IMPUESTOS (taxes):
- iva: IVA
- isr: ISR
- imss: IMSS/Seguro social

El JSON de respuesta DEBE tener esta estructura exacta:
{
  "tipo_documento": "invoice|bank_statement|sales_report|inventory|other",
  "periodo": "YYYY-MM o descripción del periodo",
  "fecha_documento": "YYYY-MM-DD si se puede identificar",
  "confianza": 0.0-1.0,
  "datos": {
    "ingresos": {
      "ventas_mostrador": 0,
      "ventas_delivery": 0,
      "ventas_app": 0,
      "otros": 0
    },
    "costos": {
      "harina": 0,
      "queso": 0,
      "pepperoni": 0,
      "vegetales": 0,
      "carnes": 0,
      "bebidas": 0,
      "otros": 0
    },
    "gastos": {
      "nomina": 0,
      "renta": 0,
      "luz": 0,
      "agua": 0,
      "gas": 0,
      "marketing": 0,
      "mantenimiento": 0,
      "otros": 0
    },
    "impuestos": {
      "iva": 0,
      "isr": 0,
      "imss": 0
    }
  },
  "alertas": [
    {
      "tipo": "string",
      "mensaje": "string",
      "severidad": "info|warning|error"
    }
  ],
  "notas": "Observaciones adicionales sobre el documento"
}
"""


class ClaudeService:
    """
    Julia: "Mi conexión con Claude para interpretar documentos financieros"
    """

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"  # Usar el modelo más reciente

    async def analyze_financial_document(
        self,
        extracted_text: str,
        document_type: Optional[str] = None,
        tables: list = None
    ) -> Dict[str, Any]:
        """
        Analiza texto extraído de un documento financiero
        Julia: "Le paso el texto a Claude y él me ayuda a estructurarlo"
        """
        # Construir el mensaje con contexto
        user_message = f"""Analiza el siguiente documento financiero y extrae los datos estructurados.

Tipo de documento sugerido: {document_type or "No identificado"}

TEXTO EXTRAÍDO:
{extracted_text[:15000]}  # Limitar para no exceder tokens
"""

        if tables:
            user_message += f"""

TABLAS EXTRAÍDAS:
{json.dumps(tables[:5], indent=2, ensure_ascii=False)}  # Primeras 5 tablas
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=FINANCIAL_EXTRACTION_PROMPT,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            # Extraer el JSON de la respuesta
            response_text = response.content[0].text

            # Intentar parsear el JSON
            json_data = self._extract_json(response_text)

            if json_data:
                logger.info("Successfully analyzed document with Claude")
                return json_data
            else:
                logger.warning("Could not extract JSON from Claude response")
                return {"error": "No se pudo extraer datos estructurados"}

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            raise

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extrae JSON de la respuesta de Claude"""
        import re

        # Buscar JSON en la respuesta
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # JSON en bloque de código
            r'```\s*([\s\S]*?)\s*```',       # Bloque de código genérico
            r'\{[\s\S]*\}',                   # JSON directo
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # Limpiar el match
                    clean_match = match.strip()
                    if not clean_match.startswith('{'):
                        continue
                    return json.loads(clean_match)
                except json.JSONDecodeError:
                    continue

        return None

    async def generate_insights(
        self,
        financial_data: Dict[str, Any],
        previous_period: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Genera insights y recomendaciones basados en los datos
        Julia: "Análisis más profundo con comparativas"
        """
        prompt = f"""Analiza estos datos financieros de Little Caesars y genera insights.

DATOS ACTUALES:
{json.dumps(financial_data, indent=2, ensure_ascii=False)}
"""

        if previous_period:
            prompt += f"""

PERIODO ANTERIOR (para comparar):
{json.dumps(previous_period, indent=2, ensure_ascii=False)}
"""

        prompt += """

Genera un análisis con:
1. Resumen ejecutivo (2-3 oraciones)
2. KPIs principales y su estado
3. Comparativa vs periodo anterior (si hay datos)
4. Top 3 alertas o áreas de atención
5. Top 3 recomendaciones accionables

Responde en JSON con esta estructura:
{
  "resumen": "string",
  "kpis": [{"nombre": "string", "valor": "string", "estado": "bueno|regular|malo"}],
  "comparativa": {"tendencia": "string", "cambios_principales": ["string"]},
  "alertas": [{"mensaje": "string", "severidad": "info|warning|error"}],
  "recomendaciones": [{"accion": "string", "impacto_estimado": "string"}]
}
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = response.content[0].text
            return self._extract_json(response_text) or {"resumen": response_text}

        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            raise

    async def answer_question(
        self,
        question: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Responde preguntas sobre los datos financieros
        Julia: "Para cuando el usuario quiere saber algo específico"
        """
        prompt = f"""Eres Julia, data scientist de Little Caesars.
El usuario tiene una pregunta sobre sus datos financieros.

CONTEXTO (datos disponibles):
{json.dumps(context, indent=2, ensure_ascii=False)}

PREGUNTA DEL USUARIO:
{question}

Responde de forma clara, directa y en español mexicano.
Si necesitas hacer cálculos, muéstralos.
Si los datos no son suficientes para responder, dilo.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Question answering failed: {e}")
            raise


# Singleton
_claude_service: Optional[ClaudeService] = None


def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service
