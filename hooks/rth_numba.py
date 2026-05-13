import os
import tempfile
os.environ.setdefault('NUMBA_CACHE_DIR', tempfile.gettempdir())
