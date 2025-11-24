import os
import logging
import subprocess
from app.config import Config

logger = logging.getLogger(__name__)

def check_ghostscript_installed():
    """Checks if Ghostscript is installed and accessible via the configured path."""
    if os.path.exists(Config.GHOSTSCRIPT_EXEC):
        logger.info(f"Ghostscript found at {Config.GHOSTSCRIPT_EXEC}.")
        return True
    else:
        logger.warning(f"Ghostscript executable not found at {Config.GHOSTSCRIPT_EXEC}. Please install Ghostscript and ensure Config.GHOSTSCRIPT_EXEC is correct.")
        return False

def compress_pdf(input_pdf_path, output_pdf_path, quality='screen'):
    """
    Compresses a PDF file using Ghostscript.
    Quality options: 'screen', 'ebook', 'printer', 'prepress', 'default'.
    """
    logger.info(f"Attempting to compress PDF: {input_pdf_path} to {output_pdf_path} with quality: {quality}")
    check_ghostscript_installed()
    gs_command = [
        Config.GHOSTSCRIPT_EXEC,
        '-sDEVICE=pdfwrite',
        '-dCompatibilityLevel=1.4',
        f'-dPDFSETTINGS=/{quality}',
        '-dNOPAUSE',
        '-dBATCH',
        '-q',
        f'-sOutputFile={output_pdf_path}',
        input_pdf_path
    ]

    try:
        subprocess.run(gs_command, check=True, capture_output=True, text=True)
        logger.info(f"Successfully compressed PDF: {input_pdf_path} -> {output_pdf_path}")
        return True
    except FileNotFoundError:
        logger.error(f"Ghostscript executable '{Config.GHOSTSCRIPT_EXEC}' not found. Cannot compress PDF. Please install Ghostscript and ensure the path is correct or it's in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error compressing PDF {input_pdf_path} with Ghostscript: {e.stderr}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during PDF compression for {input_pdf_path}: {e}", exc_info=True)
        return False
