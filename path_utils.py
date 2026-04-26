import os
import sys
from pathlib import Path

def get_path(filename: Path) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    else:
        return filename