"""
PDF Processing Service - Little Caesars Reports
Julia: "Aquí es donde la magia de extracción de datos sucede"
"""
import io
import logging
from typing import Dict, Any, List, Optional
from pdf2image import convert_from_bytes
import pytesseract
import pdfplumber
from PIL import Image

logger = logging.getLogger(__name__)


class PDFService:
    """
    Julia: "Mi servicio para procesar PDFs de todas formas y tamaños"
    """

    def __init__(self):
        self.supported_types = ["application/pdf", "image/png", "image/jpeg"]

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Extrae texto de un PDF usando múltiples métodos
        Julia: "Primero intento con pdfplumber, si no jala uso OCR"
        """
        result = {
            "text": "",
            "tables": [],
            "method": "",
            "confidence": 0.0,
            "pages": 0
        }

        # Intentar con pdfplumber primero (PDFs nativos)
        try:
            text, tables, pages = await self._extract_with_pdfplumber(pdf_bytes)
            if text and len(text.strip()) > 50:
                result["text"] = text
                result["tables"] = tables
                result["method"] = "pdfplumber"
                result["confidence"] = 0.95
                result["pages"] = pages
                logger.info("Successfully extracted with pdfplumber")
                return result
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")

        # Si no funcionó, usar OCR
        try:
            text, confidence, pages = await self._extract_with_ocr(pdf_bytes)
            result["text"] = text
            result["method"] = "ocr"
            result["confidence"] = confidence
            result["pages"] = pages
            logger.info(f"Extracted with OCR, confidence: {confidence}")
            return result
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            raise

    async def _extract_with_pdfplumber(
        self, pdf_bytes: bytes
    ) -> tuple[str, List[List[List[str]]], int]:
        """Extrae texto y tablas usando pdfplumber"""
        text_parts = []
        all_tables = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                # Extraer texto
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

                # Extraer tablas
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)

        return "\n\n".join(text_parts), all_tables, pages

    async def _extract_with_ocr(
        self, pdf_bytes: bytes
    ) -> tuple[str, float, int]:
        """Extrae texto usando OCR (para PDFs escaneados)"""
        # Convertir PDF a imágenes
        images = convert_from_bytes(pdf_bytes, dpi=300)
        pages = len(images)

        text_parts = []
        confidences = []

        for i, image in enumerate(images):
            # Preprocesar imagen para mejor OCR
            processed_image = self._preprocess_image(image)

            # Extraer texto con datos de confianza
            data = pytesseract.image_to_data(
                processed_image,
                lang='spa',
                output_type=pytesseract.Output.DICT
            )

            # Reconstruir texto
            page_text = pytesseract.image_to_string(processed_image, lang='spa')
            text_parts.append(page_text)

            # Calcular confianza promedio
            conf_values = [int(c) for c in data['conf'] if int(c) > 0]
            if conf_values:
                confidences.append(sum(conf_values) / len(conf_values) / 100)

        full_text = "\n\n".join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        return full_text, avg_confidence, pages

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Julia: "Preproceso la imagen para que el OCR jale mejor"
        - Convertir a escala de grises
        - Aumentar contraste
        - Binarizar
        """
        # Convertir a escala de grises
        if image.mode != 'L':
            image = image.convert('L')

        # Aumentar contraste (simple threshold)
        # Para producción, usar técnicas más avanzadas
        return image

    async def extract_from_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Extrae texto de una imagen directamente"""
        image = Image.open(io.BytesIO(image_bytes))
        processed = self._preprocess_image(image)

        text = pytesseract.image_to_string(processed, lang='spa')
        data = pytesseract.image_to_data(
            processed,
            lang='spa',
            output_type=pytesseract.Output.DICT
        )

        conf_values = [int(c) for c in data['conf'] if int(c) > 0]
        confidence = sum(conf_values) / len(conf_values) / 100 if conf_values else 0.5

        return {
            "text": text,
            "tables": [],
            "method": "ocr_image",
            "confidence": confidence,
            "pages": 1
        }

    def identify_document_type(self, text: str) -> str:
        """
        Julia: "Identifico qué tipo de documento es basándome en palabras clave"
        """
        text_lower = text.lower()

        # Patrones para identificar tipo de documento
        patterns = {
            "invoice": [
                "factura", "cfdi", "rfc", "subtotal", "iva", "total",
                "folio", "proveedor", "concepto"
            ],
            "bank_statement": [
                "estado de cuenta", "saldo", "movimientos", "cargo",
                "abono", "cuenta", "banco", "clabe"
            ],
            "sales_report": [
                "ventas", "tickets", "transacciones", "mostrador",
                "delivery", "total del día", "corte"
            ],
            "inventory": [
                "inventario", "stock", "existencia", "producto",
                "cantidad", "unidad", "almacén"
            ]
        }

        scores = {}
        for doc_type, keywords in patterns.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            scores[doc_type] = score

        # Retornar el tipo con mayor score
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "other"

    def extract_dates(self, text: str) -> List[str]:
        """
        Julia: "Extraigo fechas del texto"
        """
        import re

        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # DD/MM/YYYY o D/M/YY
            r'\d{1,2}-\d{1,2}-\d{2,4}',  # DD-MM-YYYY
            r'\d{4}-\d{2}-\d{2}',         # YYYY-MM-DD (ISO)
            r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}',  # 15 de enero de 2024
        ]

        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)

        return list(set(dates))

    def extract_amounts(self, text: str) -> List[Dict[str, Any]]:
        """
        Julia: "Extraigo montos y cantidades del texto"
        """
        import re

        # Patrones para montos en pesos mexicanos
        patterns = [
            r'\$[\d,]+\.?\d*',           # $1,234.56
            r'MXN\s*[\d,]+\.?\d*',       # MXN 1234.56
            r'[\d,]+\.?\d*\s*(?:pesos|MXN)',  # 1234.56 pesos
        ]

        amounts = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Limpiar y convertir a número
                clean = re.sub(r'[^\d.]', '', match)
                try:
                    value = float(clean)
                    if value > 0:
                        amounts.append({
                            "original": match,
                            "value": value
                        })
                except ValueError:
                    continue

        return amounts


# Singleton
_pdf_service: Optional[PDFService] = None


def get_pdf_service() -> PDFService:
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFService()
    return _pdf_service
