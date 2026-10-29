import io
import random

import pytest
from PIL import Image


def png(size, color=(200, 30, 30, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def banner_png() -> bytes:
    """Noisy gradient: PNG ~69 KB, lossless WebP ~44 KB, so it is converted and is far above any inline threshold."""
    random.seed(1)
    w, h = 300, 200
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            n = random.randint(-6, 6)
            px[x, y] = ((x * 255 // w + n) % 256, (y * 255 // h + n) % 256, ((x + y) * 255 // (w + h) + n) % 256)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def site_dir(tmp_path):
    """index.html + css + js + nested page + tiny icon + large noisy banner."""
    s = tmp_path / "site"
    (s / "css").mkdir(parents=True)
    (s / "js").mkdir()
    (s / "img").mkdir()
    (s / "docs").mkdir()
    (s / "index.html").write_text(
        '<!-- c --><html><head><link rel="stylesheet" href="css/app.css">'
        '<script src="js/app.js"></script><script src="js/other.js" async></script>'
        '<meta property="og:image" content="https://example.com/img/banner.png"></head>'
        '<body><img src="img/icon.png" alt="i"><img src="/img/banner.png" alt="b">'
        '<a href="docs/page.html">p</a></body></html>')
    (s / "docs" / "page.html").write_text(
        '<html><body><img src="../img/icon.png"><script src="../js/app.js"></script>'
        '<script>boot()</script></body></html>')
    (s / "css" / "app.css").write_text("body { background: url(../img/icon.png); color: red; }\n")
    (s / "js" / "app.js").write_text("// hi\nwindow.boot = function () { return 1; };\n")
    (s / "js" / "other.js").write_text("var x = 1;\n")
    (s / "img" / "icon.png").write_bytes(png((4, 4)))
    (s / "img" / "banner.png").write_bytes(banner_png())
    return s
