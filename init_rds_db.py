from app import create_app, db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

def init_db():
    with app.app_context():
        try:
            logger.info("Limpando banco de dados RDS (drop tables)...")
            db.drop_all()
            logger.info("Criando tabelas no banco de dados RDS...")
            db.create_all()
            logger.info("Tabelas criadas com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao criar tabelas: {e}")

if __name__ == "__main__":
    init_db()
