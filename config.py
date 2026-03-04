import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "outlook_parser.db")
DB_URL = f"sqlite:///{DB_PATH}"

HOST = "127.0.0.1"
PORT = 8765

LOG_LEVEL = "info"
