import brotli
import gzip
from pathlib import Path

def compress(data: bytes):
    brotli_size = len(brotli.compress(data))
    compressed = gzip.compress(data)
    return compressed, brotli_size

def write_sidecars(path: Path, minified_bytes: bytes, output_dir: Path):
    name = path.name
    base = output_dir / name
    with open(base, 'wb') as f:
        f.write(minified_bytes)
    compressed, brotli_size = compress(minified_bytes)
    gz_path = output_dir / (name + '.gz')
    with open(gz_path, 'wb') as f:
        f.write(compressed)
    br_path = output_dir / (name + '.br')
    with open(br_path, 'wb') as f:
        f.write(brotli.compress(minified_bytes))
    return gz_path.stat().st_size, brotli_size
