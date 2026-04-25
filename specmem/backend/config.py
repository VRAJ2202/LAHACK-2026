"""
SpecMem configuration — loads environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI: str = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "specmem")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required")
