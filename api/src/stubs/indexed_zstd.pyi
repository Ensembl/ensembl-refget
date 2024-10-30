from pathlib import Path
from io import BufferedReader

class IndexedZstdFile(BufferedReader):
    name: str

    def __init__(self, filename: str | Path) -> None: ...
