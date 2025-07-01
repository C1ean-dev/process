from .handlers import PDFProcessor

# Instancia o processador uma vez para reutilização
_pdf_processor = PDFProcessor()

def normalize_text(text):
    """Normaliza o texto usando o método da classe PDFProcessor."""
    return _pdf_processor._normalize_text(text)

def extract_text_from_pdf(pdf_path):
    """Extrai texto de um PDF usando o método da classe PDFProcessor."""
    return _pdf_processor.extract_text_from_pdf(pdf_path)

def extract_data_from_text(text):
    """Extrai dados estruturados do texto usando o método da classe PDFProcessor."""
    return _pdf_processor.extract_structured_data(text)