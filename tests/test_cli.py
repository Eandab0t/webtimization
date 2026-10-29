import gzip
import json
import re
import subprocess
import sys

import brotli
from click.testing import CliRunner

from webtim.cli import main


def run(*args):
    r = CliRunner().invoke(main, [str(a) for a in args])
    assert r.exit_code == 0, r.output
    return r.output


def test_default_run_keeps_tree_and_writes_sidecars(site_dir, tmp_path):
    out = tmp_path / "out"
    run(site_dir, "-o", out)
    # tree layout preserved (the old CLI flattened css/app.js and js/app.js onto each other)
    for rel in ["index.html", "docs/page.html", "css/app.css", "js/app.js", "img/icon.png", "img/banner.png"]:
        assert (out / rel).is_file(), rel
    html = (out / "index.html").read_text()
    assert "<!--" not in html
    assert gzip.decompress((out / "index.html.gz").read_bytes()).decode() == html
    assert brotli.decompress((out / "index.html.br").read_bytes()).decode() == html
    assert not (out / "img/icon.png.gz").exists()  # images are not recompressed


def test_dry_run_writes_nothing_and_does_not_crash(site_dir, tmp_path):
    out = tmp_path / "out"
    text = run(site_dir, "-o", out, "--dry-run", "-v")
    assert not out.exists()
    assert "Totals:" in text and "brotli" in text


def test_full_pipeline(site_dir, tmp_path):
    out = tmp_path / "out"
    run(site_dir, "-o", out, "--webp", "--inline-small", 2048, "--defer-scripts", "--hash", "--emit-config", "nginx")
    index = (out / "index.html").read_text()
    # icon: webp first (a 4x4 PNG shrinks), then inlined as that webp, and its file dropped
    assert "data:image/webp;base64," in index
    assert not list(out.glob("img/icon*"))
    banners = list(out.glob("img/banner.*.webp"))
    assert len(banners) == 1 and banners[0].name in index
    # og:image absolute URL still resolves: the original banner.png was kept
    assert (out / "img/banner.png").is_file() and "https://example.com/img/banner.png" in index
    # hashed css/js referenced from html; app.js deferred, async other.js untouched
    app_js = next(p.name for p in (out / "js").glob("app.*.js"))
    assert re.search(rf'<script src="?js/{app_js}"? defer', index)
    assert not re.search(r"other\.[0-9a-f]{8}\.js[^>]*defer", index)
    # nested page: relative ref rewritten with ../ ; page has inline code, so it must NOT be deferred
    page = (out / "docs/page.html").read_text()
    assert f"../js/{app_js}" in page and "defer" not in page
    # css url(../img/icon.png) was converted and inlined too
    css = next((out / "css").glob("app.*.css")).read_text()
    assert "data:image/webp;base64," in css
    # config sits NEXT TO the output dir, never inside the served tree
    assert (tmp_path / "out.nginx.conf").is_file() and not list(out.glob("*.conf"))


def test_single_file_input(site_dir, tmp_path):
    out = tmp_path / "o"
    run(site_dir / "js" / "app.js", "-o", out)
    assert (out / "app.js").is_file()


def test_output_inside_input_is_not_reprocessed(site_dir):
    run(site_dir, "-o", site_dir / "dist")
    run(site_dir, "-o", site_dir / "dist")  # second run must not walk into dist/
    assert not (site_dir / "dist" / "dist").exists()


def test_undecodable_and_unminifiable_files_survive(site_dir, tmp_path):
    (site_dir / "js" / "latin.js").write_bytes("var s = 'caf\xe9';".encode("latin-1"))
    out = tmp_path / "out"
    run(site_dir, "-o", out)
    assert (out / "js/latin.js").read_bytes() == "var s = 'caf\xe9';".encode("latin-1")


def test_webp_flag_without_pillow_is_a_clear_error(site_dir, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    r = CliRunner().invoke(main, [str(site_dir), "--webp", "--dry-run"])
    assert r.exit_code != 0 and "Pillow" in r.output


def test_no_web_files(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert "No HTML/CSS/JS" in run(tmp_path)


def test_identity_is_one_name():
    """The project answers to `webtim` everywhere: version text, help usage, package."""
    import webtim
    from webtim.serve import main as serve_main

    version = CliRunner().invoke(main, ["--version"]).output.strip()
    assert version == f"webtim, version {webtim.__version__}"

    usage = CliRunner().invoke(main, ["--help"], prog_name="webtim").output
    assert "Usage: webtim [OPTIONS] INPUT" in usage
    assert CliRunner().invoke(serve_main, ["--version"]).output.strip() == (
        f"webtim-serve, version {webtim.__version__}"
    )

