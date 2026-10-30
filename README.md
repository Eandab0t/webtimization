# WebTimize Compressor

Local-first, build-time optimizer for static sites. It minifies HTML/CSS/JS, writes Brotli and gzip
sidecars, optionally converts/inlines images, cache-busts assets, defers scripts, and emits
nginx/Caddy configuration. The Python package and both commands remain named `webtim`.

```bash
pip install -e ".[images]"          # Pillow only needed for --webp
webtim ./site -o ./dist -v          # minify + .gz/.br sidecars
webtim ./site -o ./dist --webp --inline-small 2048 --defer-scripts --hash --emit-config nginx
webtim ./site --dry-run             # sizes only, writes nothing
webtim ./site -o ./dist --report build-report.json
webtim --version
webtim-serve ./dist                 # small deployments; production should use nginx/Caddy
```

`python -m webtim` does the same thing as `webtim`.

## What each option does (all off by default except minify + sidecars)

| Option | Effect | Skips / limits |
|---|---|---|
| *(default)* | Minify HTML/CSS/JS; write `.gz` and `.br` next to text files, only when smaller than the original | Non-UTF-8 files and minifier errors: file copied unchanged with a warning. JS containing a nested template literal is left unminified |
| `--webp` | PNG/JPEG to WebP when smaller (lossless for PNG, q80 for JPEG); rewrites references | No `<picture>` fallback |
| `--inline-small BYTES` | Images up to BYTES become `data:` URIs in HTML/CSS (SVG is URL-encoded, the rest base64); the file is dropped if nothing else names it | Can increase total bytes; measure with `--report`. Hurts caching if the page is shared by many routes |
| `--defer-scripts` | Adds `defer` to external classic scripts | Pages with inline classic scripts are skipped entirely; module/async/already-deferred scripts untouched |
| `--hash` | Renames assets to `name.<sha256[:8]>.ext`, rewrites references, so they can be cached for a year | JS/CSS that another JS/CSS file names (e.g. `import "./util.js"`) is not renamed. References built at runtime are invisible. An asset still named by an absolute URL (og:image, manifest) is left unhashed and reported, instead of shipping a second copy |
| `--emit-config nginx\|caddy` | Writes `<out>.nginx.conf` / `<out>.caddy.conf` **next to** the output dir | `brotli_static` is emitted commented out: it needs the ngx_brotli module |
| `--report PATH` | Writes a machine-readable JSON build report | Written even for `--dry-run`; dry-run sizes are estimates |

Pipeline order: minify CSS/JS, WebP, inline, hash, defer, minify HTML, compress.
HTML is minified last because the rewriting regexes expect the author's markup.

## Output safety

- The input directory is never modified.
- A build writes to a temporary staging directory, validates sidecars by decompressing them back to
  the original bytes, and only then replaces the output directory.
- A failed validation leaves the previous output untouched.
- A successful build replaces the output directory, so files from an earlier run are not left behind.
- `--dry-run` writes no output (it may still write a requested `--report`).

## Build report

`--report build-report.json` emits a versioned report:

```json
{
  "schema_version": 1,
  "status": "ok",
  "counts": { "discovered": 12, "processed": 12, "skipped": 0, "failed": 0, "output_files": 13 },
  "sizes": {
    "original_bytes": 184320,
    "output_bytes": 141900,
    "saved_bytes": 42420,
    "saved_percent": 23.0,
    "gzip_wire_bytes": 39120,
    "brotli_wire_bytes": 34210
  },
  "transformations": { "minified": 8, "webp": 2, "inlined": 1, "hashed": 6, "hashed_skipped": 0, "deferred": 3, "dropped": 1 },
  "duration_ms": 214
}
```

`status` is `ok`, `partial` (some transform failed and its file was copied unchanged), or
`no_web_files`. Per-file output records include `path`, `bytes`, `gzip_bytes`, and `brotli_bytes`.
`gzip_wire_bytes`/`brotli_wire_bytes` use the smaller generated sidecar (or the original when no
sidecar was written) and exclude HTTP overhead. For `--dry-run`, `sizes_are_estimated` is `true`.
`hashed_skipped` counts assets left unhashed because an absolute URL still names them; each one also
appears in `warnings`, so a build never hides why an asset kept its original name.

## Cache policy it generates

- Hashed files: `Cache-Control: public, max-age=31536000, immutable`
- Everything else (HTML included): `no-cache` (revalidate with ETag)

## Tests

`pytest` (needs Pillow; node is used for JS round-trip tests when present). Current baseline: **46
tests passing**. The nginx output was checked against a real nginx 1.24 (`nginx -t` and curl).
Brotli serving and the Caddy snippet were **not** run against real servers.

## Layout

```text
webtim/            package: cli, build orchestration, serve, serve_config, transforms, minifiers, compress
tests/             pytest suite
docs/              competitive and technical research
SOURCES.md         why each default was chosen, and what was verified
```

## Known limitations

- Reference rewriting is regex-based; runtime-built URLs and every modern JS import form are not
  visible to it.
- Hashing leaves an asset alone when an absolute URL names it, because the deploy host is unknown;
  those assets keep their original names and miss long-term caching. They are counted as
  `hashed_skipped` and listed as warnings.
- Inlining trades request count for bytes; it is not automatically a net win.
- `htmlmin` imports the deprecated `cgi` module, which is removed in Python 3.13.
- Browser-level visual validation is not part of this tool; test representative sites before
  deploying transformed output.

See [docs/competitive-research.md](docs/competitive-research.md) for the build-tool landscape and
the recommended next priorities.
