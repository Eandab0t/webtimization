import gzip
import threading
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from webtim.cli import main
from webtim.serve import Handler
from webtim.serve_config import caddy, nginx
from webtim.transforms import HASHED_RE


@pytest.fixture
def served(site_dir, tmp_path):
    out = tmp_path / "out"
    assert CliRunner().invoke(main, [str(site_dir), "-o", str(out), "--hash"]).exit_code == 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield out, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url, enc=""):
    req = urllib.request.Request(url, headers={"Accept-Encoding": enc} if enc else {})
    with urllib.request.urlopen(req) as r:
        return r.status, dict(r.headers), r.read()


def test_serves_brotli_then_gzip_then_plain(served):
    out, base = served
    status, h, body = get(base + "/", "gzip, br")
    assert status == 200 and h["Content-Encoding"] == "br" and h["Content-Type"].startswith("text/html")
    assert h["Vary"] == "Accept-Encoding"
    status, h, body = get(base + "/index.html", "gzip")
    assert h["Content-Encoding"] == "gzip" and gzip.decompress(body) == (out / "index.html").read_bytes()
    status, h, body = get(base + "/index.html")
    assert "Content-Encoding" not in h and body == (out / "index.html").read_bytes()


def test_cache_headers_hashed_vs_html(served):
    out, base = served
    css = next((out / "css").glob("app.*.css")).name
    assert get(f"{base}/css/{css}")[1]["Cache-Control"] == "public, max-age=31536000, immutable"
    assert get(base + "/index.html")[1]["Cache-Control"] == "no-cache"


def test_hashed_regex_matches_only_fingerprinted_names():
    import re
    assert re.search(HASHED_RE, "/js/app.0123abcd.js")
    assert not re.search(HASHED_RE, "/js/app.js") and not re.search(HASHED_RE, "/js/app.0123abcdef.js")


def test_config_snippets_contain_the_directives_the_sources_describe():
    n = nginx("/srv/site")
    assert "gzip_static on;" in n and "# brotli_static on;" in n and "immutable" in n and '"\\.[0-9a-f]{8}' in n
    c = caddy("/srv/site")
    assert "precompressed br gzip" in c and "path_regexp hashed" in c and "immutable" in c
