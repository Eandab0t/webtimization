import gzip
from pathlib import Path

import brotli


def compress(data: bytes) -> tuple[bytes, bytes]:
    """Return (gzip, brotli). mtime=0 keeps gzip output reproducible."""
    return gzip.compress(data, 9, mtime=0), brotli.compress(data)


def write_sidecars(path: Path, data: bytes, output_dir: Path) -> tuple[int, int]:
    """Write <name>, <name>.gz, <name>.br into output_dir; return (gzip size, brotli size)."""
    gz, br = compress(data)
    (output_dir / path.name).write_bytes(data)
    (output_dir / (path.name + ".gz")).write_bytes(gz)
    (output_dir / (path.name + ".br")).write_bytes(br)
    return len(gz), len(br)
