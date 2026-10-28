import pytest
from pathlib import Path
from arachni_opt.compress import compress, write_sidecars


def test_compression_reduces_size():
    data = b"<html><body>Hello World! Hello again!</body></html>" * 10
    compressed, brotli_size = compress(data)
    assert len(compressed) < len(data)
    assert brotli_size < len(data)


def test_write_sidecars(tmp_path):
    data = b"<html><body>test</body></html>"
    fake_path = Path('/tmp/fake.html')
    gz_size, br_size = write_sidecars(fake_path, data, tmp_path)
    assert (tmp_path / 'fake.html').exists()
    assert (tmp_path / 'fake.html.gz').exists()
    assert (tmp_path / 'fake.html.br').exists()
