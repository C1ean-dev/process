import os
import hashlib
import logging
from app.config import Config

logger = logging.getLogger(__name__)

def calculate_checksum(filepath):
    """Calculates the SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as file:
            while True:
                chunk = file.read(4096)  # Read in 4KB chunks
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating checksum for {filepath}: {e}")
        return None

def check_duplicates(filepath, db_session, File):
    """
    Checks if a file with the same checksum already exists in the database.
    Returns True if a duplicate is found, False otherwise.
    """
    checksum = calculate_checksum(filepath)
    if not checksum:
        return False

    existing_file = db_session.query(File).filter_by(checksum=checksum).first()
    if existing_file:
        logger.info(f"Duplicate file found: {filepath} (Checksum: {checksum}, Existing File ID: {existing_file.id})")
        return True
    else:
        logger.info(f"No duplicate found for {filepath} (Checksum: {checksum})")
        return False

def process_file_for_duplicates(file_id, filepath, db, File, db_session):
    """
    Processes a file to check for duplicates and updates the database accordingly.
    This function should be called from the main worker task.
    """
    try:
        # Calculate checksum and check for duplicates
        checksum = calculate_checksum(filepath)
        if not checksum:
            logger.warning(f"Could not calculate checksum for {filepath}. Skipping duplicate check.")
            return False  # Treat as not a duplicate

        # Update the file record with the checksum
        file_record = db_session.query(File).get(file_id)
        if file_record:
            file_record.checksum = checksum
            db_session.commit()
            logger.info(f"Updated file {file_id} with checksum: {checksum}")

            # Now check for duplicates
            existing_file = db_session.query(File).filter(File.checksum == checksum, File.id != file_id).first() # Exclude current file
            if existing_file:
                logger.info(f"Duplicate file found: {filepath} (Checksum: {checksum}, Existing File ID: {existing_file.id})")
                return True
            else:
                logger.info(f"No duplicate found for {filepath} (Checksum: {checksum})")
                return False
        else:
            logger.warning(f"File record not found for ID: {file_id}")
            return False

    except Exception as e:
        logger.error(f"Error processing file {filepath} for duplicates: {e}", exc_info=True)
        db_session.rollback()
        return False
