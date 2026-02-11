import psycopg2
import os
from app.config import Config

# Using URL from Config instead of hardcoded values
db_url = Config.SQLALCHEMY_DATABASE_URI

print(f"Tentando conectar usando a URL definida no Config.")

def test_connection():
    print(f"\n--- Testando conexão com RDS ---")
    try:
        conn = psycopg2.connect(db_url)
        print("CONECTADO COM SUCESSO!")
        cur = conn.cursor()
        cur.execute('SELECT version();')
        print(f"Versão do Servidor: {cur.fetchone()[0]}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Falha na conexão: {e}")
        return False

if __name__ == "__main__":
    test_connection()
