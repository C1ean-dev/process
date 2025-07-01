from .handlers import DuplicateChecker

def process_file_for_duplicates(file_id, filepath, db_session, File):
    """
    Ponto de entrada para a verificação de duplicatas.
    Instancia e usa a classe DuplicateChecker para processar o arquivo.
    """
    checker = DuplicateChecker()
    return checker.process_file(file_id, filepath, db_session, File)