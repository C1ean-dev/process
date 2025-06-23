import logging
import os # Added for os.path.exists and os.path.join
import sys # Added for sys.platform
import re
import unicodedata
from pypdf import PdfReader
from pdf2image import convert_from_path
import pytesseract
from app.config import Config

logger = logging.getLogger(__name__)

def check_tesseract_installed():
    """Checks if Tesseract OCR is installed and accessible."""
    try:
        pytesseract.get_tesseract_version()
        logger.info("Tesseract OCR is installed and accessible.")
        return True
    except pytesseract.TesseractNotFoundError:
        logger.warning("Tesseract OCR is not found. Please install it and ensure it's in your system's PATH, or set pytesseract.pytesseract.tesseract_cmd correctly.")
        return False
    except Exception as e:
        logger.warning(f"Error checking Tesseract installation: {e}")
        return False

def check_poppler_installed():
    """Checks if Poppler (pdftoppm) is installed and accessible via the configured path."""
    poppler_pdftoppm_path = os.path.join(Config.POPPLER_PATH, 'pdftoppm.exe') if sys.platform == "win32" else os.path.join(Config.POPPLER_PATH, 'pdftoppm')
    if os.path.exists(poppler_pdftoppm_path):
        logger.info(f"Poppler (pdftoppm) found at {poppler_pdftoppm_path}.")
        return True
    else:
        logger.warning(f"Poppler (pdftoppm) not found at {poppler_pdftoppm_path}. Please install Poppler and ensure Config.POPPLER_PATH is correct.")
        return False

def normalize_text(text):
    """Converts text to lowercase and removes accents, preserving hyphens."""
    normalized_text = unicodedata.normalize('NFD', text)
    normalized_text = normalized_text.encode('ascii', 'ignore').decode('utf-8').lower()
    return normalized_text

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file using OCR if direct extraction fails."""
    logger.info(f"Attempting to extract text directly from PDF: {pdf_path}")
    text = ""
    try:
        # Use pypdf for direct text extraction
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        
        if text.strip():
            logger.info(f"Successfully extracted text directly from PDF: {pdf_path}")
            return text
        else:
            logger.info(f"No direct text extracted from {pdf_path}, attempting OCR.")

    except Exception as e:
        logger.warning(f"Direct text extraction failed for {pdf_path}: {e}. Attempting OCR.")
    
    # --- OCR Logic controlled by feature flag ---
    if Config.ENABLE_OCR:
        # Perform checks before attempting OCR
        tesseract_ok = check_tesseract_installed()
        poppler_ok = check_poppler_installed()

        if not tesseract_ok:
            logger.error("Tesseract is not installed or configured correctly. Skipping OCR.")
            return text # Return text extracted so far (could be empty)
        if not poppler_ok:
            logger.error("Poppler is not installed or configured correctly. Skipping OCR.")
            return text # Return text extracted so far (could be empty)

        try:
            # Use pdf2image and pytesseract for OCR
            images = convert_from_path(pdf_path, poppler_path=Config.POPPLER_PATH)
            for i, image in enumerate(images):
                logger.info(f"Performing OCR on page {i+1} of {pdf_path}")
                page_text = pytesseract.image_to_string(image, lang='por')
                text += page_text + "\n"
            logger.info(f"Successfully extracted text from PDF using OCR: {pdf_path}")
        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path} using OCR: {e}. Ensure Tesseract and Poppler are installed and configured correctly.", exc_info=True)
    else:
        logger.info(f"OCR skipped for {pdf_path} as feature flag is disabled.")
    # --- End OCR Logic ---
    return text

def extract_data_from_text(text):
    """Extracts specific data points from the given text."""
    data = {
        "nome": None,
        "matricula": None,
        "funcao": None,
        "empregador": None,
        "rg": None,
        "cpf": None,
        "equipamentos": [], # Keep this for the equipment names
        "imei_numbers": [], # New list for IMEI numbers
        "patrimonio_numbers": [], # New list for Patrimonio numbers
        "data": None
    }

    # Nome: ao que tiver entre empregado: e matricula:
    nome_match = re.search(r"empregado:\s*(.*?)\s*matricula:", text, re.DOTALL | re.IGNORECASE)
    if nome_match:
        data["nome"] = nome_match.group(1).strip()

    # Matricula: ao que tiver entre matricula: e função
    matricula_match = re.search(r"matricula:\s*(.*?)\s*funcao:", text, re.DOTALL | re.IGNORECASE)
    if matricula_match:
        data["matricula"] = matricula_match.group(1).strip()

    # Função: ao que tiver entre função e r.g:
    funcao_match = re.search(r"funcao:\s*(.*?)(?:\s*r\.g\.|\s*empregador:|\n|$)", text, re.DOTALL | re.IGNORECASE)
    if funcao_match:
        data["funcao"] = funcao_match.group(1).strip()

    # RG: ao que tiver entre rgn = e empregador:
    rg_match = re.search(r"r\.g\.\s*n(?:º|°)?:\s*(.*?)\s*empregador:", text, re.DOTALL | re.IGNORECASE)
    if rg_match:
        data["rg"] = rg_match.group(1).strip()

    # Empregador: ao que tiver entre empregador: e cpf:
    empregador_match = re.search(r"empregador:\s*(.*?)\s*cpf:", text, re.DOTALL | re.IGNORECASE)
    if empregador_match:
        data["empregador"] = empregador_match.group(1).strip()

    # CPF: ao que tiver entre cpf e ( )
    cpf_match = re.search(r"cpf:\s*(.*?)\s*\(\s*\)", text, re.DOTALL | re.IGNORECASE)
    if cpf_match:
        data["cpf"] = cpf_match.group(1).strip()
        if not data["cpf"]: # Keep this logic to ensure empty string if no CPF found
            data["cpf"] = ""

    # Equipamentos - This regex remains the same as it was working
    equipamentos_block_match = re.search(r"ferramentas:\s*(.*?)\s*declaro", text, re.DOTALL | re.IGNORECASE)
    if equipamentos_block_match:
        equipamentos_block = equipamentos_block_match.group(1).strip()
        
        for line in equipamentos_block.split('\n'):
            line = line.strip()
            if not line:
                continue

            current_line_text = line # Use a clear variable for the current line
            imei = None
            patrimonio = None

            # Extract IMEI first
            imei_match = re.search(r"imei:\s*(\S+)", current_line_text, re.IGNORECASE)
            if imei_match:
                imei = imei_match.group(1).strip()
                data["imei_numbers"].append(imei)
                current_line_text = re.sub(r"imei:\s*\S+", "", current_line_text, flags=re.IGNORECASE).strip() # Remove IMEI part

            # Extract Patrimonio next
            patrimonio_match = re.search(r"patrimonio:\s*(\S+)", current_line_text, re.IGNORECASE)
            if patrimonio_match:
                patrimonio = patrimonio_match.group(1).strip()
                data["patrimonio_numbers"].append(patrimonio)
                current_line_text = re.sub(r"patrimonio:\s*\S+", "", current_line_text, flags=re.IGNORECASE).strip() # Remove Patrimonio part
            
            # The remaining text is the equipment name
            equipment_name_final = re.sub(r"^equipamento:\s*", "", current_line_text, flags=re.IGNORECASE).strip()

            if equipment_name_final:
                equipment_info = {"nome_equipamento": equipment_name_final}
                # Only add imei/patrimonio to equipment_info if they were found and are not None
                if imei:
                    equipment_info["imei"] = imei
                if patrimonio:
                    equipment_info["patrimonio"] = patrimonio
                data["equipamentos"].append(equipment_info)

    # Date - porra de regex no site funciona aqui não wtffff
    date_match = re.search(r"sao paulo,\s*(\d{1,2})\s+de\s+([a-zA-Zçãõéúíóáàêôâü]+)\s+de\s+(\d{4})\s*empregado", text, re.DOTALL | re.IGNORECASE)
    if date_match:
        day = date_match.group(1).strip()
        month_name = date_match.group(2).strip()
        year = date_match.group(3).strip()
        
        month_mapping = {
            "janeiro": "01", "fevereiro": "02", "marco": "03", "abril": "04", "maio": "05", "junho": "06",
            "julho": "07", "agosto": "08", "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"
        }
        month = month_mapping.get(month_name, "00")
        logger.info(f"verificando mes: {month}")
        if month != "00":
            data["data"] = f"{day}/{month}/{year}"
        else:
            logger.warning(f"Could not parse month name: {month_name}")
    return data
