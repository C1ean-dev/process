import sys
import os

# Add the parent directory to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, start_workers, shutdown_workers # Import start_workers and shutdown_workers
import atexit # Import atexit

from dotenv import load_dotenv 
load_dotenv()


app = create_app()

if __name__ == '__main__':
    start_workers(app) # Start workers here
    atexit.register(shutdown_workers, app) # Register shutdown hook, passing app instance
    app.run(debug=True, use_reloader=False)
