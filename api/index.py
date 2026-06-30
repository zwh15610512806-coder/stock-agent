from pathlib import Path
import sys


api_root = Path(__file__).resolve().parent
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

from app.main import app  # noqa: E402,F401
