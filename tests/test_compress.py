import gzip
from pathlib import Path

import brotli

from webtim.compress import compress, write_sidecars


def test_compression_reduces_size_and_round_trips():
    data = b"<html><body>Hello World! Hello again!</body></html>" * 10
    gz, br = compress(data)
    assert len(gz) < len(data) and len(br) < len(data)
    assert gzip.decompress(gz) == data and brotli.decompress(br) == data


def test_gzip_is_reproducible():
    assert compress(b"abc" * 100)[0] == compress(b"abc" * 100)[0]


def test_write_sidecars(tmp_path):
    data = b"<html><body>test</body></html>" * 5
    gz_size, br_size = write_sidecars(Path("/tmp/fake.html"), data, tmp_path)
    assert (tmp_path / "fake.html").read_bytes() == data
    assert (tmp_path / "fake.html.gz").stat().st_size == gz_size
    assert (tmp_path / "fake.html.br").stat().st_size == br_size
