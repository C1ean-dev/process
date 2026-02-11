import hashlib
import logging

logger = logging.getLogger(__name__)

class DuplicateChecker:
    def _calculate_checksum(self, filepath):
        """Calcula o checksum SHA-256 de um arquivo."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(4096):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError as e:
            logger.error(f"Error calculating checksum for {filepath}: {e}", exc_info=True)
            return None

    def process_file(self, file_id, filepath, db_session, File):
        """
        Processa um arquivo para verificar duplicatas e atualiza o checksum no banco de dados.
        Retorna True se um duplicado for encontrado, False caso contrário.
        """
        try:
            checksum = self._calculate_checksum(filepath)
            if not checksum:
                logger.warning(f"Could not calculate checksum for {filepath}. Skipping duplicate check.")
                return False

            file_record = db_session.get(File, file_id)
            if not file_record:
                logger.warning(f"File record not found for ID: {file_id} during duplicate check.")
                return False

            file_record.checksum = checksum
            if checksum:
                existing_file = db_session.query(File).filter(
                    File.checksum == checksum,
                    File.id != file_id
                ).first()
                db_session.commit()

            if existing_file:
                logger.info(f"Duplicate file found: {filepath} (Checksum: {checksum}, Existing File ID: {existing_file.id})")
                return True
            else:
                logger.info(f"No duplicate found for {filepath} (Checksum: {checksum})")
                return False
        except Exception as e:
            logger.error(f"Error processing file {filepath} for duplicates: {e}", exc_info=True)
            db_session.rollback()
            return False
