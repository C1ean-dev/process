import sys
import os

# Add the parent directory to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, start_workers, shutdown_workers # Import start_workers and shutdown_workers
from app.config import Config
import atexit # Import atexit

from dotenv import load_dotenv
load_dotenv()

app = create_app()

def recreate_db():
    """Recreate database - USE WITH CAUTION: This will delete all data!"""
    env = Config.FLASK_ENV
    if env == 'production':
        print("ERROR: Cannot recreate database in production environment!")
        print("Use 'python -m app recreate_db' only in development.")
        return

    confirm = input("This will DELETE ALL DATA. Are you sure? (type 'yes' to confirm): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return

    with app.app_context():
        print("Shutting down workers...")
        shutdown_workers(app)
        print("Recreating database...")
        from app import db
        db.drop_all()
        db.create_all()
        print("Database recreated successfully.")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'recreate_db':
        recreate_db()
    else:
        start_workers(app)  # Start workers here
        atexit.register(shutdown_workers, app)  # Register shutdown hook, passing app instance
        app.run(debug=True, use_reloader=False)
