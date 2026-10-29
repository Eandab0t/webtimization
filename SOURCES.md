# Sources, tools and decisions

Everything used to build and verify this, and what each source was used for.
Retrieved 2026-10-28. Web sources informed design choices; behaviour claims about the code itself
were verified by running it (see "Verified here").

## Process
- **ponytail** (plugin skill): scope rule used throughout: smallest complete change, every transform opt-in, a test or self-check for each non-trivial piece, and a `shortcut: <limit>, <when to upgrade>` comment wherever a known limit remains (grep `shortcut:`).

## Software used (versions as installed in the build sandbox)
Python 3.12.3, click 8.3.1, htmlmin 0.1.12, cssmin 0.2.0, **rjsmin 1.3.0**, brotli 1.2.1, Pillow 12.1.1, pytest 9.2.0, Node v22.22.2 (JS round-trip tests), nginx 1.24.0 (config verification).
`jsmin` was removed, see below.

## What was wrong and what changed (found by reading and running the original code)
| Problem in 0.1.0 | Evidence | Fix |
|---|---|---|
| Three names for one project: the distribution, the command and the import package all differed | `pip show` reported 0.1.0, installed a differently named command and depended on `jsmin`, while the source was 0.2.0 | one name, `webtim`, for the distribution, package, both commands and the docs; version single-sourced from `webtim/__init__.py`; stale `*.egg-info` and the old editable install removed |
| `--dry-run` crashed | `gzip`/`brotli` imported inside `if out is not None` but used after it | imports at top, compress via `compress.py` |
| `html_minify.minify()` raised `TypeError` | `htmlmin.Minifier.minify()` has no `remove_optional_closing_tags` kwarg; probed directly | parameter removed |
| HTML comments never removed (its own test asserts they are) | probed: default `Minifier()` keeps them | `remove_comments=True` |
| Output flattened to one directory | `out / target.name` | relative paths kept |
| Non-web files not copied | only HTML/CSS/JS were written | all files copied through |
| `brotli` missing from dependencies | `pyproject.toml` | added |
| `tests/test_cli.py` imported `process_file` and `bench`, which never existed | read the file | replaced by tests of the real CLI |
| `jsmin` corrupts template literals: `` `x ${1+1} y` `` became `x 2y` | node round-trip test failed | switched to rjsmin; rjsmin still corrupts a template nested inside `${}` (probed), so those files are left unminified |
| `write_sidecars` compressed Brotli twice; `compress()` returned a size, not bytes | read | `compress()` returns `(gzip, brotli)` bytes; test updated |
| Sidecars could be larger than the source | tiny files | sidecar written only if smaller |

## Verified here (not from web sources)
- 39 pytest tests pass.
- Generated nginx snippet: `nginx -t` OK on nginx 1.24; curl showed `Content-Encoding: gzip` served from the `.gz` sidecar (48 B for a 1500 B CSS), `Cache-Control: public, max-age=31536000, immutable` on the hashed file, `no-cache` on HTML, `Vary: Accept-Encoding`.
- Not verified: Brotli serving (nginx here has no ngx_brotli), the Caddy snippet, behaviour on real-world sites.

## Web sources
**Cache headers for fingerprinted files** (immutable + one-year max-age; HTML short or no-cache; immutable only safe when the URL changes with content)
- https://specification.website/spec/performance/cache-control/
- https://stackharbor.com/en/knowledge-base/nginx-static-asset-caching/
- https://csswizardry.com/2023/10/what-is-the-maximum-max-age/
- https://docs.serverpod.dev/next/concepts/web-server/static-files.md (same rule, immutable reserved for cache-busted assets)

**Serving precompressed files**
- nginx `gzip_static` is in the default distribution; `brotli_static` needs the ngx_brotli module; both can be used together: https://docs.rs/static-compress
- ngx_brotli static module serves pre-compressed `.br` files: https://github.com/globalopsteam/ngx_brotli (mirror of google/ngx_brotli)
- Caddy `file_server { precompressed ... }` looks for `.br`/`.gz`/`.zst` sidecars in the listed order: https://caddyserver.com/docs/caddyfile/directives/file_server
- Precompressing removes per-request CPU cost: https://irbr.ru/en/blog/nginx-brotli-gzip-static-optimization/

**Inlining images as base64**: base64 is ~33% larger; small icons benefit, large images and shared images do not.
The sources **disagree on the break-even**: roughly 1 KB on HTTP/2 (freetoolonline image guide), ~4 KB (freetoolonline base64 guide, HTTP/1.1-era), under ~8 KB (moda.app). `--inline-small` therefore has no default; README suggests 2048.
- https://openreplay.com/tools/image-to-base64/
- https://freetoolonline.com/guides/en/base64-when-to-use-and-when-not-to.html
- https://freetoolonline.com/guides/en/image-to-base64-embed-in-html-vs-link.html
- https://dev.to/jeromell/when-and-when-not-to-inline-images-as-base64-2abo
- https://moda.app/tools/image-to-base64 (SVG: URL-encode instead of base64, usually smaller)

**`defer`**: runs after parsing in document order; no effect on module scripts (deferred by default).
- https://developer.mozilla.org/en/HTML/Element/Script
- https://rocketvalidator.com/html-validation/a-script-element-with-type-module-must-not-have-a-defer-attribute

**WebP**: Google reports lossless WebP 26% smaller than PNG, lossy 25-34% smaller than comparable JPEG: https://developers.google.com/speed/webp (these are Google's figures, results vary per image, which is why `--webp` keeps the original unless WebP is actually smaller).

## From the conversation
The EanHost logo write-up supplied by the user (1,176-byte WebP, base64 expansion to 1,568 characters, HTML growing by 3,627 bytes) is the reason for the inline-size warning and the "embedding does not compress" note.
