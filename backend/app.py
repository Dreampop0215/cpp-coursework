import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import create_app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("BACKEND_PORT", "5000")))
