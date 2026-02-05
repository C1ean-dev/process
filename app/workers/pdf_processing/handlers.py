import logging
import os
import sys
import re
import unicodedata
from pypdf import PdfReader
from pdf2image import convert_from_path
import pytesseract
from app.config import Config

logger = logging.getLogger(__name__)

class PDFProcessor:
    """
    Encapsula a lógica de processamento de PDF, incluindo extração de texto e dados.
    """

    def __init__(self):
        pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD
        self.tesseract_ok = self._check_tesseract_installed()
        self.poppler_ok = self._check_poppler_installed()

    def _check_tesseract_installed(self):
        try:
            pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR is installed and accessible.")
            return True
        except pytesseract.TesseractNotFoundError:
            logger.warning("Tesseract OCR not found. OCR will be unavailable.")
            return False
        except Exception as e:
            logger.warning(f"Error checking Tesseract installation: {e}")
            return False

    def _check_poppler_installed(self):
        if sys.platform != "win32":
            # Em não-Windows, assume-se que está no PATH se instalado.
            return True
        poppler_pdftoppm_path = os.path.join(Config.POPPLER_PATH, 'pdftoppm.exe')
        if os.path.exists(poppler_pdftoppm_path):
            logger.info(f"Poppler (pdftoppm) found at {Config.POPPLER_PATH}.")
            return True
        else:
            logger.warning(f"Poppler not found at {Config.POPPLER_PATH}. OCR will be unavailable.")
            return False

    def _normalize_text(self, text):
        normalized = unicodedata.normalize('NFD', text)
        return normalized.encode('ascii', 'ignore').decode('utf-8').lower()

    def extract_text_from_pdf(self, pdf_path):
        logger.info(f"Attempting to extract text from PDF: {pdf_path}")
        text = self._direct_text_extraction(pdf_path)
        if not text.strip() and Config.ENABLE_OCR:
            logger.info(f"No direct text found in {pdf_path}, attempting OCR.")
            text = self._ocr_text_extraction(pdf_path)
        elif not text.strip():
            logger.info(f"Direct text extraction for {pdf_path} was empty. OCR is disabled.")
        return text

    def _direct_text_extraction(self, pdf_path):
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PdfReader(file)
                num_pages = len(reader.pages)
                if num_pages > Config.MAX_PDF_PAGES:
                    logger.warning(f"PDF {pdf_path} exceeds maximum pages ({num_pages} > {Config.MAX_PDF_PAGES}). Processing only first {Config.MAX_PDF_PAGES} pages.")
                    pages_to_process = reader.pages[:Config.MAX_PDF_PAGES]
                else:
                    pages_to_process = reader.pages

                for page in pages_to_process:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                logger.info(f"Successfully extracted text directly from {pdf_path}")
        except Exception as e:
            logger.warning(f"Direct text extraction failed for {pdf_path}: {e}")
        return text

    def _ocr_text_extraction(self, pdf_path):
        if not self.tesseract_ok or not self.poppler_ok:
            logger.error("OCR dependencies (Tesseract/Poppler) not met. Skipping OCR.")
            return ""
        text = ""
        try:
            # First check page count without converting everything
            with open(pdf_path, 'rb') as file:
                reader = PdfReader(file)
                num_pages = len(reader.pages)
            
            if num_pages > Config.MAX_PDF_PAGES:
                logger.warning(f"PDF {pdf_path} exceeds maximum pages for OCR. Processing only first {Config.MAX_PDF_PAGES} pages.")
                last_page = Config.MAX_PDF_PAGES
            else:
                last_page = num_pages

            images = convert_from_path(pdf_path, last_page=last_page, poppler_path=Config.POPPLER_PATH)
            for i, image in enumerate(images):
                logger.info(f"Performing OCR on page {i+1} of {pdf_path} (Limit: {last_page})")
                text += pytesseract.image_to_string(image, lang='por') + "\n"
            logger.info(f"Successfully extracted text using OCR from {pdf_path}")
        except Exception as e:
            logger.error(f"Error during OCR extraction for {pdf_path}: {e}", exc_info=True)
        return text

    def extract_structured_data(self, text):
        normalized_text = self._normalize_text(text)
        data = {
            "nome": self._extract_field(normalized_text, r"empregado:\s*(.*?)\s*matricula:"),
            "matricula": self._extract_field(normalized_text, r"matricula:\s*(.*?)\s*funcao:"),
            "funcao": self._extract_field(normalized_text, r"funcao:\s*(.*?)(?:\s*r\.g\.|\s*empregador:|\n|$)"),
            "rg": self._extract_field(normalized_text, r"r\.g\.\s*n(?:º|°)?:\s*(.*?)\s*empregador:"),
            "empregador": self._extract_field(normalized_text, r"empregador:\s*(.*?)\s*cpf:"),
            "cpf": self._extract_field(normalized_text, r"cpf:\s*(.*?)\s*\(\s*\)"),
            "data": self._extract_date(normalized_text)
        }
        data.update(self._extract_equipment_data(normalized_text))
        return data

    def _extract_field(self, text, pattern):
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_date(self, text):
        date_match = re.search(r"sao paulo,\s*(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", text)
        if not date_match:
            return None
        day, month_name, year = date_match.groups()
        month_map = {
            "janeiro": "01", "fevereiro": "02", "marco": "03", "abril": "04", "maio": "05", "junho": "06",
            "julho": "07", "agosto": "08", "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"
        }
        month = month_map.get(month_name.lower())
        return f"{day.zfill(2)}/{month}/{year}" if month else None

    def _extract_equipment_data(self, text):
        data = {"equipamentos": [], "imei_numbers": [], "patrimonio_numbers": []}
        equip_block_match = re.search(r"ferramentas:\s*(.*?)\s*declaro", text, re.DOTALL | re.IGNORECASE)
        if not equip_block_match:
            return data

        for line in equip_block_match.group(1).strip().split('\n'):
            line = line.strip()
            if not line: continue

            imei = self._extract_field(line, r"imei:\s*(\S+)")
            if imei: 
                data["imei_numbers"].append(imei)
                line = re.sub(r"imei:\s*\S+", "", line, flags=re.IGNORECASE).strip()

            patrimonio = self._extract_field(line, r"patrimonio:\s*(\S+)")
            if patrimonio:
                data["patrimonio_numbers"].append(patrimonio)
                line = re.sub(r"patrimonio:\s*\S+", "", line, flags=re.IGNORECASE).strip()
            
            equip_name = re.sub(r"^equipamento:\s*", "", line, flags=re.IGNORECASE).strip()
            if equip_name:
                equip_info = {"nome_equipamento": equip_name}
                if imei: equip_info["imei"] = imei
                if patrimonio: equip_info["patrimonio"] = patrimonio
                data["equipamentos"].append(equip_info)
        return data
