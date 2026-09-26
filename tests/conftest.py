import sys
from pathlib import Path

# generator/ and ingestion/ are run as standalone scripts (cd into the
# directory, `python event_generator.py`), not installed packages — so
# their modules aren't importable by name unless their directories are on
# sys.path. Tests want to import the real modules directly rather than
# shelling out, so add both here once for the whole test session.
ROOT = Path(__file__).resolve().parent.parent
for subdir in ("generator", "ingestion"):
    path = str(ROOT / subdir)
    if path not in sys.path:
        sys.path.insert(0, path)
