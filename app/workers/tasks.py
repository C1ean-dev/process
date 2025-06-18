from __future__ import annotations # This must be the very first line
import os
import logging
import pytesseract
from PIL import Image
from pypdf import PdfReader # Keep pypdf for now, though extract_text_from_pdf uses it internally
from multiprocessing import Process, Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import File
from app.config import Config # Import Config to access folder paths

# New imports for PDF extraction logic
import re
import subprocess
from pdf2image import convert_from_path
import unicodedata
import json # For storing equipments as JSON

# Configure logging for workers
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set Tesseract, Poppler, and Ghostscript paths from Config
pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD
poppler_path = Config.POPPLER_PATH # Used directly by pdf2image
ghostscript_exec = Config.GHOSTSCRIPT_EXEC # Used directly by subprocess

# New functions from user's provided code
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

def check_ghostscript_installed():
    """Checks if Ghostscript is installed and accessible via the configured path."""
    if os.path.exists(Config.GHOSTSCRIPT_EXEC):
        logger.info(f"Ghostscript found at {Config.GHOSTSCRIPT_EXEC}.")
        return True
    else:
        logger.warning(f"Ghostscript executable not found at {Config.GHOSTSCRIPT_EXEC}. Please install Ghostscript and ensure Config.GHOSTSCRIPT_EXEC is correct.")
        return False

def normalize_text(text):
    """Converts text to lowercase and removes accents, preserving hyphens."""
    normalized_text = unicodedata.normalize('NFD', text)
    normalized_text = normalized_text.encode('ascii', 'ignore').decode('utf-8').lower()
    return normalized_text

def compress_pdf(input_pdf_path, output_pdf_path, quality='screen'):
    """
    Compresses a PDF file using Ghostscript.
    Quality options: 'screen', 'ebook', 'printer', 'prepress', 'default'.
    """
    logger.info(f"Attempting to compress PDF: {input_pdf_path} to {output_pdf_path} with quality: {quality}")
    
    gs_command = [
        ghostscript_exec,
        '-sDEVICE=pdfwrite',
        '-dCompatibilityLevel=1.4',
        '-dNOPAUSE',
        '-dBATCH',
        '-q',
        # Explicit image compression and downsampling for aggressive reduction
        '-dColorImageResolution=50', # Lowered resolution for more aggressive compression
        '-dGrayImageResolution=50',  # Lowered resolution for more aggressive compression
        '-dMonoImageResolution=50',  # Lowered resolution for more aggressive compression
        '-dColorImageDownsampleType=/Bicubic',
        '-dGrayImageDownsampleType=/Bicubic',
        '-dMonoImageDownsampleType=/Bicubic',
        '-dColorImageCompression=/DCTEncode', # JPEG compression for color images
        '-dGrayImageCompression=/DCTEncode', # JPEG compression for grayscale images
        '-dMonoImageCompression=/CCITTFaxEncode', # CCITTFax compression for monochrome images (good for scanned text)
        '-dEmbedAllFonts=false', # Do not embed all fonts
        '-dSubsetFonts=true', # Subset fonts if embedded (only embed used characters)
        '-dDetectDuplicateImages=true', # Detect and reuse duplicate images
        '-dCompressPages=true', # Compress page content streams
        '-dFastWebView=true', # Optimize for web viewing (linearize PDF)
        '-dEncodeColorImages=true', # Ensure images are re-encoded
        '-dEncodeGrayImages=true',
        '-dEncodeMonoImages=true',
        '-dAutoFilterColorImages=true', # Auto-select best filter for color images
        '-dAutoFilterGrayImages=true',
        '-dAutoFilterMonoImages=true',
        '-dJPEGQ=50', # Set JPEG quality for DCTEncode (0-100, lower is more compression)
        f'-sOutputFile={output_pdf_path}',
        input_pdf_path
    ]

    try:
        subprocess.run(gs_command, check=True, capture_output=True, text=True)
        logger.info(f"Successfully compressed PDF: {input_pdf_path} -> {output_pdf_path}")
        return True
    except FileNotFoundError:
        logger.error(f"Ghostscript executable '{ghostscript_exec}' not found. Cannot compress PDF. Please install Ghostscript and ensure the path is correct or it's in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error compressing PDF {input_pdf_path} with Ghostscript: {e.stderr}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during PDF compression for {input_pdf_path}: {e}", exc_info=True)
        return False

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
        try:
            # Use pdf2image and pytesseract for OCR
            images = convert_from_path(pdf_path, poppler_path=poppler_path) # Pass poppler_path explicitly
            for i, image in enumerate(images):
                logger.info(f"Performing OCR on page {i+1} of {pdf_path}")
                page_text = pytesseract.image_to_string(image, lang='por')
                text += page_text + "\n"
            logger.info(f"Successfully extracted text from PDF using OCR: {pdf_path}")
        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path} using OCR: {e}. Make sure Tesseract and Poppler are installed and configured correctly.")
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

def process_file_task(file_id: int, file_path: str, current_retries: int, results_queue: Queue):
    """
    Worker function to process a single file (OCR).
    This function runs in a separate process and sends results back via a queue.
    """
    current_status = 'processing'
    processed_data = ""
    extracted_structured_data = {} # To store the dictionary of extracted data
    new_retries = current_retries # Initialize new_retries with the current value
    original_file_path = file_path # Store the original path for logging/reference
    new_file_path = file_path # This will be updated as the file moves

    try:
        logger.info(f"Worker {os.getpid()} attempting to process file ID: {file_id} from path: {file_path} (Attempt: {current_retries + 1})")

        filename = os.path.basename(file_path) # file_path is now always from PENDING_FOLDER
        
        # 1. Move file from PENDING_FOLDER to PROCESSING_FOLDER
        processing_path = os.path.join(Config.PROCESSING_FOLDER, filename)
        try:
            if os.path.exists(file_path): # Ensure file exists in PENDING_FOLDER before moving
                os.rename(file_path, processing_path)
                new_file_path = processing_path
                logger.info(f"File {filename} moved from {Config.PENDING_FOLDER} to {Config.PROCESSING_FOLDER}")
            else:
                raise FileNotFoundError(f"File not found at {file_path} in PENDING_FOLDER.")
        except Exception as e:
            logger.error(f"Error moving file {file_path} to {Config.PROCESSING_FOLDER}: {e}")
            current_status = 'failed'
            new_retries += 1
            processed_data = f"Error moving file to processing folder: {e}"
            # If move fails, we can't proceed, so send result and return
            results_queue.put((file_id, current_status, processed_data.strip(), new_retries, file_path, extracted_structured_data)) # Pass empty structured data
            logger.info(f"Worker {os.getpid()} sent result for file ID {file_id} to results queue (move to processing failed).")
            return # Exit early if file cannot be moved to processing

        file_extension = os.path.splitext(new_file_path)[1].lower() # Use new_file_path for extension
        logger.info(f"Worker {os.getpid()} processing file type: {file_extension}")

        if file_extension in ['.png', '.jpg', '.jpeg', '.gif']:
            try:
                img = Image.open(new_file_path) # Process from new_file_path
                extracted_text = pytesseract.image_to_string(img, lang='por') # Specify language
                if extracted_text:
                    processed_data = extracted_text
                    logger.info(f"Worker {os.getpid()} - Image extracted text (first 50 chars): {extracted_text[:50]}...")
                else:
                    logger.warning(f"Worker {os.getpid()} - Image extraction returned empty for file ID {file_id}.")
            except Exception as e:
                logger.error(f"Error processing image file {new_file_path}: {e}", exc_info=True)
                processed_data = f"Error processing image: {e}"
                current_status = 'failed'
                new_retries += 1
        elif file_extension == '.pdf':
            # Use the new extract_text_from_pdf function
            processed_data = extract_text_from_pdf(new_file_path)
            if not processed_data.strip():
                logger.warning(f"Worker {os.getpid()} - PDF extraction (direct or OCR) returned empty for file ID {file_id}.")
            
            # --- PDF Compression Logic ---
            if Config.ENABLE_PDF_COMPRESSION and current_status != 'failed': # Only attempt compression if enabled and not already failed
                original_pdf_in_processing = new_file_path # This is the path to the uncompressed PDF
                compressed_pdf_filename = f"compressed_{filename}"
                compressed_pdf_path = os.path.join(Config.PROCESSING_FOLDER, compressed_pdf_filename)

                logger.info(f"Attempting to compress PDF for file ID {file_id}...")
                if compress_pdf(original_pdf_in_processing, compressed_pdf_path):
                    logger.info(f"PDF compressed successfully for file ID {file_id}. Original: {original_pdf_in_processing}, Compressed: {compressed_pdf_path}")
                    # Update new_file_path to point to the compressed file
                    new_file_path = compressed_pdf_path
                    # Delete the original uncompressed PDF from the processing folder
                    try:
                        os.remove(original_pdf_in_processing)
                        logger.info(f"Original uncompressed PDF removed from processing folder: {original_pdf_in_processing}")
                    except Exception as e:
                        logger.warning(f"Could not remove original uncompressed PDF {original_pdf_in_processing}: {e}")
                else:
                    logger.error(f"PDF compression failed for file ID {file_id}. File will be moved to FAILED_FOLDER.")
                    current_status = 'failed'
                    new_retries += 1
                    processed_data += "\nWarning: PDF compression failed."
                    # If compression fails, keep new_file_path as the original uncompressed file
                    # so it can be moved to FAILED_FOLDER.
                    new_file_path = original_pdf_in_processing
            else:
                if not Config.ENABLE_PDF_COMPRESSION:
                    logger.info(f"PDF compression skipped for file ID {file_id} as feature flag is disabled.")
            # --- End PDF Compression Logic ---
        else:
            processed_data = "Unsupported file type."
            current_status = 'failed'
            new_retries += 1
            logger.warning(f"Unsupported file type for {new_file_path}")

        # Log the final extracted data (raw text)
        if processed_data and processed_data.strip(): # Check if it's not just whitespace
            # Extract structured data from the raw text
            extracted_structured_data = extract_data_from_text(normalize_text(processed_data))
        else:
            logger.warning(f"Worker {os.getpid()} - Final raw processed_data is empty or whitespace for file ID {file_id}. Status: {current_status}. No structured data extracted.")
            extracted_structured_data = {} # Ensure it's an empty dict if no text

        # Determine final destination based on processing status
        final_destination_folder = None
        if current_status != 'failed':
            current_status = 'completed'
            final_destination_folder = Config.COMPLETED_FOLDER
        else:
            final_destination_folder = Config.FAILED_FOLDER
        
        # 2. Move file to final destination (COMPLETED_FOLDER or FAILED_FOLDER)
        try:
            if final_destination_folder:
                final_path = os.path.join(final_destination_folder, filename)
                os.rename(new_file_path, final_path)
                new_file_path = final_path # Update new_file_path to the final folder
                logger.info(f"File {filename} moved from {Config.PROCESSING_FOLDER} to {final_destination_folder}")
        except Exception as e:
            logger.error(f"Error moving file {new_file_path} to {final_destination_folder}: {e}", exc_info=True) # Log full traceback
            # If moving fails, still mark as completed/failed but log the error
            processed_data += f"\nWarning: Could not move file to final folder: {e}"
            # Keep new_file_path as the processing_path if move failed
            new_file_path = processing_path 

        logger.info(f"Worker {os.getpid()} finished processing file ID: {file_id}. Final Status: {current_status}")

    except Exception as e:
        logger.error(f"Worker {os.getpid()} - An unexpected error occurred during file processing for ID {file_id}: {e}", exc_info=True)
        current_status = 'failed'
        new_retries += 1
        processed_data = f"Processing failed due to unexpected error: {e}"
        extracted_structured_data = {} # Ensure empty on unexpected error
        # If an unexpected error occurs, try to move to FAILED_FOLDER
        try:
            filename = os.path.basename(file_path) # Use filename from PENDING_FOLDER
            failed_path = os.path.join(Config.FAILED_FOLDER, filename)
            # Check if file is still in processing_path or original_file_path
            if os.path.exists(new_file_path): # Check if it's in processing folder
                os.rename(new_file_path, failed_path)
                new_file_path = failed_path
                logger.info(f"File {filename} moved to {Config.FAILED_FOLDER} due to unexpected error.")
            elif os.path.exists(file_path): # Check if it's still in PENDING_FOLDER (shouldn't be if moved to processing)
                os.rename(file_path, failed_path)
                new_file_path = failed_path
                logger.info(f"File {filename} moved to {Config.FAILED_FOLDER} due to unexpected error (from pending path).")
            else:
                logger.warning(f"Could not find file {filename} to move to FAILED_FOLDER after unexpected error.")
                new_file_path = file_path # Keep original path if cannot move
        except Exception as move_e:
            logger.error(f"Error moving file to FAILED_FOLDER after unexpected error: {move_e}", exc_info=True) # Log full traceback
            new_file_path = file_path # Keep original path if cannot move

    finally:
        # Send result back to the main application via the results queue
        # Include the updated retry count, the new file path, and the extracted structured data
        results_queue.put((file_id, current_status, processed_data.strip(), new_retries, new_file_path, extracted_structured_data))
        logger.info(f"Worker {os.getpid()} sent result for file ID {file_id} to results queue.")


def worker_main(task_queue: Queue, results_queue: Queue, db_uri: str): # db_uri is no longer used directly by worker
    """
    Main loop for a worker process.
    Continuously fetches tasks from the task_queue and processes them,
    sending results to the results_queue.
    """
    logger.info(f"Worker process started. PID: {os.getpid()}. Listening for tasks...")
    while True:
        try:
            # task_queue now sends file_id, file_path, and current_retries
            file_id, file_path, current_retries = task_queue.get() # Blocks until a task is available
            if file_id is None: # Sentinel value to stop the worker
                logger.info(f"Worker process {os.getpid()} received stop signal. Exiting.")
                break
            logger.info(f"Worker {os.getpid()} received task: File ID {file_id}, Path: {file_path}, Retries: {current_retries}")
            # Pass current_retries to process_file_task
            process_file_task(file_id, file_path, current_retries, results_queue)
        except Exception as e:
            logger.error(f"Worker {os.getpid()} - Error in worker main loop: {e}", exc_info=True)
            # If an error occurs before putting to results_queue, ensure it's handled
            # This might happen if file_id or file_path are malformed
            # Send a failed status with incremented retries (if file_id is known)
            # Also send the original file_path as new_file_path in case of worker_main error
            results_queue.put((file_id if 'file_id' in locals() else None, 'failed', f"Worker main loop error: {e}", (current_retries + 1) if 'current_retries' in locals() else 0, file_path if 'file_path' in locals() else None, {})) # Pass empty structured data

# This part is for running the worker independently if needed, or for testing
if __name__ == '__main__':
    # Example usage (for testing the worker independently)
    # In a real Flask app, you'd manage these processes from app/__init__.py or a separate script
    from app import create_app # Import create_app to get config
    app = create_app()
    with app.app_context():
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    # Create a queue for tasks
    q = Queue()

    # Start a worker process
    worker_process = Process(target=worker_main, args=(q, db_uri))
    worker_process.start()

    # Example: Add a dummy task to the queue
    # You would replace this with actual file IDs and paths from your Flask app
    # q.put((1, '/path/to/your/file.png'))

    # To stop the worker, put a sentinel value
    # q.put((None, None))
    # worker_process.join()
