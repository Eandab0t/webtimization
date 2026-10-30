"""Whole-site transforms. A site is a dict {relative PurePosixPath: bytes}.

Every transform is opt-in (see cli.py) because each one changes the HTML/asset graph.
"""
import base64
import hashlib
import io
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import quote

TEXT = {".html", ".css", ".js"}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".webp": "image/webp", ".svg": "image/svg+xml"}
HASHABLE = {".css", ".js", ".woff", ".woff2", ".ttf", ".otf"} | set(MIME)
HASH_LEN = 8
# One regex shared by serve.py and the nginx/Caddy snippets so "hashed" means the same everywhere.
HASHED_RE = r"\.[0-9a-f]{%d}\.[A-Za-z0-9]+$" % HASH_LEN

Site = dict  # PurePosixPath -> bytes


def _text(site: Site, p: PurePosixPath) -> str:
    return site[p].decode("utf-8")


def _resolve(page: PurePosixPath, ref: str) -> PurePosixPath | None:
    """Map a reference found in `page` to a site path; None for external/data/anchor refs."""
    ref = re.split(r"[?#]", ref, maxsplit=1)[0]
    if not ref or re.match(r"^([a-z][a-z0-9+.-]*:|//)", ref, re.I):
        return None
    base = "/" if ref.startswith("/") else str(page.parent)
    path = posixpath.normpath(posixpath.join(base, ref)).lstrip("/")
    return PurePosixPath(path)


def rewrite_refs(site: Site, renames: dict) -> None:
    """Replace every quoted/url() reference to a renamed file, relative or root-relative."""
    for page in [p for p in site if p.suffix in TEXT]:
        text = _text(site, page)
        for old, new in renames.items():
            rel_old = posixpath.relpath(old, page.parent)
            rel_new = posixpath.relpath(new, page.parent)
            for o, n in ((rel_old, rel_new), ("/" + str(old), "/" + str(new))):
                text = re.sub(r"(?<![\w./-])(\./)?" + re.escape(o) + r"(?=[\s\"'`)?#>,;]|$)",
                              lambda m, n=n: (m.group(1) or "") + n, text)
        site[page] = text.encode("utf-8")


def _rename(site: Site, moves: dict) -> None:
    """moves: {old: (new, new_bytes)}. Rewrites refs, but keeps `old` when some text still names it
    (og:image / manifest absolute URLs cannot be rewritten safely, so both copies ship)."""
    old_bytes = {o: site.pop(o) for o in moves}
    for o, (n, b) in moves.items():
        site[n] = b
    rewrite_refs(site, {o: n for o, (n, _) in moves.items()})
    corpus = "\n".join(_text(site, p) for p in site if p.suffix in TEXT)
    for o in moves:
        if o.name in corpus:
            site[o] = old_bytes[o]


# shortcut: no <picture> fallback, every current browser decodes WebP; add one if you must support ancient ones
def to_webp(site: Site) -> dict:
    """PNG/JPEG -> WebP when Pillow is installed and the result is smaller. Returns the renames."""
    try:
        from PIL import Image
    except ImportError:
        return {}
    moves = {}
    for p in [p for p in site if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]:
        try:
            img = Image.open(io.BytesIO(site[p]))
            buf = io.BytesIO()
            # lossless for PNG keeps pixels exact; JPEG is already lossy so q80 is a fair match
            img.save(buf, "WEBP", lossless=(img.format == "PNG"), quality=80, method=6)
        except Exception:
            continue  # unreadable/animated/odd image: leave it untouched
        if len(buf.getvalue()) < len(site[p]):
            moves[p] = (p.with_suffix(".webp"), buf.getvalue())
    _rename(site, moves)
    return {o: n for o, (n, _) in moves.items()}


_REF = re.compile(r"""((?:src\s*=\s*|url\()\s*["']?)([^"'\s)>]+)""", re.I)


# shortcut: inlining into a page shared by many routes defeats caching, keep the threshold small
def inline_small(site: Site, max_bytes: int, dropped: list | None = None) -> int:
    """Replace refs to images <= max_bytes with data: URIs, then drop files nothing references. Returns count."""
    inlined = set()

    def sub(page):
        def f(m):
            target = _resolve(page, m.group(2))
            data = site.get(target)
            if data is None or target.suffix.lower() not in MIME or len(data) > max_bytes:
                return m.group(0)
            inlined.add(target)
            mime = MIME[target.suffix.lower()]
            if target.suffix.lower() == ".svg":  # SVG is text: URL-encoding beats base64's +33%
                return f"{m.group(1)}data:{mime},{quote(data.decode('utf-8'), safe='/:')}"
            return f"{m.group(1)}data:{mime};base64,{base64.b64encode(data).decode()}"
        return f

    for page in [p for p in site if p.suffix in {".html", ".css"}]:
        site[page] = _REF.sub(sub(page), _text(site, page)).encode("utf-8")
    still_used = "\n".join(_text(site, p) for p in site if p.suffix in TEXT)
    for t in inlined:
        if t.name not in still_used:
            del site[t]
            if dropped is not None:
                dropped.append(t)
    return len(inlined)


_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)


def _is_inline_code(attrs: str, body: str) -> bool:
    """Classic inline script. Data blocks (JSON-LD, importmap) and modules don't break under defer."""
    if re.search(r"\bsrc\s*=", attrs, re.I) or not body.strip():
        return False
    t = re.search(r"type\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.I)
    return not t or t.group(1).lower() == "text/javascript"


def defer_scripts(site: Site) -> int:
    """Add `defer` to external classic scripts. Skips any page that also has inline code,
    because deferring an external script can break an inline script that uses its globals."""
    count = 0
    for page in [p for p in site if p.suffix == ".html"]:
        html = _text(site, page)
        tags = _SCRIPT.findall(html)
        if any(_is_inline_code(a, body) for a, body in tags):
            continue

        def f(m):
            nonlocal count
            attrs = m.group(1)
            if (not re.search(r"\bsrc\s*=", attrs, re.I)
                    or re.search(r"\b(defer|async)\b|type\s*=\s*[\"']?module", attrs, re.I)):
                return m.group(0)  # module scripts already defer; async/defer already set
            count += 1
            return f"<script{attrs} defer>{m.group(2)}</script>"

        site[page] = _SCRIPT.sub(f, html).encode("utf-8")
    return count


# shortcut: refs built at runtime ("img/" + name + ".png") are invisible here, use a bundler for those sites
def hash_names(site: Site) -> dict:
    """Rename assets to name.<sha256[:8]>.ext so they can be cached forever. Returns the renames.

    Pass 1 hashes leaves (images/fonts) and rewrites refs; pass 2 hashes css/js, whose bytes
    now include the leaf renames. css/js that another css/js file refers to by name are left
    alone: renaming them would break imports we cannot safely rewrite after hashing.
    """
    def rename(paths):
        moves = {p: (p.with_name(f"{p.stem}.{hashlib.sha256(site[p]).hexdigest()[:HASH_LEN]}{p.suffix}"), site[p])
                 for p in paths}
        _rename(site, moves)
        return {o: n for o, (n, _) in moves.items()}

    renames = rename([p for p in site if p.suffix.lower() in HASHABLE - {".css", ".js"}])
    code = [p for p in site if p.suffix in {".css", ".js"}]
    others = {p: _text(site, p) for p in code}
    safe = [p for p in code if not any(p.name in t for q, t in others.items() if q != p)]
    renames.update(rename(safe))
    return renames
