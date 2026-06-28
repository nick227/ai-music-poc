"""Start the FastAPI dev server. Prefer ./scripts/dev_bootstrap.sh for validated ACE paths."""
from app.main import run_dev_server

if __name__ == "__main__":
    run_dev_server()
