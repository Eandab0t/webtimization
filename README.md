# webtim

Offline optimizer for static sites: minify HTML/CSS/JS, precompress with Brotli and gzip,
optionally cache-bust, inline tiny images, convert to WebP, defer scripts, and emit
nginx/Caddy config (or serve it with a stdlib server) so the precompressed files are actually used.

```bash
pip install -e ".[images]"          # Pillow only needed for --webp
webtim ./site -o ./dist -v          # minify + .gz/.br sidecars, nothing else changes
webtim ./site -o ./dist --webp --inline-small 2048 --defer-scripts --hash --emit-config nginx
webtim ./site --dry-run             # sizes only, writes nothing
webtim --version
webtim-serve ./dist                 # small deployments; production should use nginx/Caddy
```

`python -m webtim` does the same thing as `webtim`.

## What each option does (all off by default except minify + sidecars)

| Option | Effect | Skips / limits |
|---|---|---|
| *(default)* | Minify HTML/CSS/JS; write `.gz` and `.br` next to text files, only when smaller than the original | Non-UTF-8 files and minifier errors: file copied unchanged with a warning. JS containing a nested template literal is left unminified (the minifier would corrupt it) |
| `--webp` | PNG/JPEG to WebP when smaller (lossless for PNG, q80 for JPEG); rewrites references | No `<picture>` fallback |
| `--inline-small BYTES` | Images up to BYTES become `data:` URIs in HTML/CSS (SVG is URL-encoded, the rest base64); the file is dropped if nothing else names it | Hurts caching if the page is shared by many routes. 2048 is a starting point, sources disagree on the break-even (see SOURCES.md) |
| `--defer-scripts` | Adds `defer` to external classic scripts | Pages with inline classic scripts are skipped entirely; module/async/already-deferred scripts untouched |
| `--hash` | Renames assets to `name.<sha256[:8]>.ext`, rewrites references, so they can be cached for a year | JS/CSS that another JS/CSS file names (e.g. `import "./util.js"`) is not renamed. References built at runtime are invisible. If an absolute URL (og:image, manifest) still names the old file, the original is kept too |
| `--emit-config nginx\|caddy` | Writes `<out>.nginx.conf` / `<out>.caddy.conf` **next to** the output dir | `brotli_static` is emitted commented out: it needs the ngx_brotli module |

Pipeline order (it matters): minify CSS/JS, WebP, inline, hash, defer, minify HTML, compress.
HTML is minified last because the rewriting regexes expect the author's markup.

## Cache policy it generates
- Hashed files: `Cache-Control: public, max-age=31536000, immutable`
- Everything else (HTML included): `no-cache` (revalidate with ETag)

## Tests
`pytest` (needs Pillow; node is used for JS round-trip tests when present). The nginx output was
also checked against a real nginx 1.24 (`nginx -t` and curl). Brotli serving and the Caddy snippet
were **not** run against real servers.

## Layout

```
webtim/            package: cli, serve, serve_config, transforms, the three minifiers, compress
tests/             pytest suite
SOURCES.md         why each default was chosen, and what was verified
```

## Changes from 0.1.0
One name everywhere: the distribution, import package, both commands (`webtim`, `webtim-serve`) and
the docs agree, and the version lives in a single place, `webtim/__init__.py`. See SOURCES.md,
"What was wrong and what changed".
