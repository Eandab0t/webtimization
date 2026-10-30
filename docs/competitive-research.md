# WebTimize Compressor — competitive and technical research

Research date: 2026-10-30. Sources were read directly; search-result snippets were not treated as evidence.
This document covers build-time asset optimization. It deliberately excludes browser-side cleanup, which belongs to WebTimize Live.

## 1. Competitor overview

The market splits into measurement tools and transform tools. Neither category currently closes the loop “audit built output, safely transform it, report exact before/after bytes” without adopting a Node/Chrome toolchain.

| Product | Category | What it does | What it does not do | License |
|---|---|---|---|---|
| [Lighthouse](https://developer.chrome.com/docs/lighthouse/overview) / [Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci) | Measurement | Audits a served URL; budgets and CI reporting | Does not modify output | Apache-2.0 |
| [Unlighthouse](https://unlighthouse.dev/) | Measurement | Crawls a site and runs Lighthouse at scale | Does not modify output; JS crawler is limited | MIT |
| [WebPageTest](https://www.webpagetest.org/about) | Measurement | Real-browser diagnostics and scripting | Does not modify output | Polyform Shield (source-available, not OSI) |
| [Parcel](https://parceljs.org/features/production/) | Build tool | Bundles, minifies, hashes, image transforms via Sharp | Requires source adoption; no byte-level post-build report | MIT |
| [Vite](https://vite.dev/guide/build.html) | Build tool | Bundling, hashed assets, tree-shaking | `public/` assets stay unhashed; no image pipeline | MIT |
| [Next.js](https://nextjs.org/docs/app/api-reference/components/image) | Framework | Image/font optimization tied to runtime | Static export needs a custom loader; not framework-neutral | MIT |
| [Hugo Pipes](https://gohugo.io/functions/resources/minify/) | SSG built-in | Minify and fingerprint resources | Opt-in per template; no site-level report | Apache-2.0 |
| [jekyll-minifier](https://github.com/digitalsparky/jekyll-minifier) | SSG plugin | Minifies HTML/CSS/JS in production | GPL-3.0; no fingerprinting; Jekyll-only | GPL-3.0 |
| [html-minifier-terser](https://github.com/terser/html-minifier-terser) | Standalone minifier | Highly configurable per-file minification | No asset graph, hashing, images, or report | MIT |

## 2. Relevant open-source projects

### Minification engines

- **[minify-html](https://github.com/wilsonzlin/minify-html)** — Rust core with PyO3 wheels for Python 3.8–3.14. WHATWG-aware whitespace handling, template-syntax preservation, optional inline JS/CSS minification. MIT. This is the highest-value dependency available to a Python optimizer because it avoids running Node for HTML.
- **[rjsmin](https://github.com/ndparker/rjsmin)** — Pure-Python/optional-C token minifier. Apache-2.0, active. No mangling or dead-code elimination, so it is a fallback rather than a competitive JS minifier.
- **[Terser](https://github.com/terser/terser)** — Mature JS minifier with source maps and license-comment preservation. BSD-2-Clause. Requires Node.
- **[esbuild](https://esbuild.github.io/api/)** — Go binary with a string-to-string `transform` API; fast, MIT, practical to shell out to. Roughly 5–10% larger output than Terser-class tools.
- **[oxc-minify](https://github.com/oxc-project/oxc)** — Rust minifier, MIT; strong on large inputs. No Python bindings.
- **[Lightning CSS](https://lightningcss.dev/)** — Rust CSS parser/minifier/transformer. MPL-2.0 core; Node CLI. Python bindings exist (`lightningcss` on PyPI) but are alpha.
- **[cssnano](https://cssnano.github.io/cssnano/)** — PostCSS plugin suite, MIT. Safe-by-default preset; slower than Lightning CSS.
- **[SVGO](https://github.com/svg/svgo)** — Plugin-based SVG optimizer, MIT. Node CLI/library; can be over-aggressive on animated/reference-heavy SVGs.

### Images and fonts

- **[Sharp](https://sharp.pixelplumbing.com/)** — libvips-based image pipeline, Apache-2.0. Fast, supports AVIF/WebP, but not usable directly from Python.
- **Pillow** — Python imaging library. Version 11.3+ ships AVIF read/write in wheels. Current optional dependency; suitable for conservative conversions.
- **[imagemin](https://github.com/imagemin/imagemin)** — Wrapper around per-format binaries; legacy design, no AVIF focus. GPL-family binaries such as pngquant/gifsicle must not be bundled into a permissively licensed product without review.

### Fingerprinting and reporting

- **Django `ManifestStaticFilesStorage`** — content-hashed filenames plus post-processing of CSS `url()`/`@import` and source-map comments. Good reference for dependency-ordered hashing, but regex rewriting has limits.
- **Vite/Parcel manifests** — content hashes on emitted assets; HTML is served `no-cache` so new hashes are picked up.
- **Critical CSS**: [critical](https://github.com/addyosmani/critical) and Beasties/Penthouse. Browser-free used-CSS extraction is fast but not viewport-aware; Puppeteer/Playwright extraction is accurate but heavy. Not a first-release feature for a zero-browser Python CLI.

## 3. Technologies and libraries worth evaluating

| Need | Current WebTimize approach | Candidate improvement | Why not now |
|---|---|---|---|
| HTML minify | `htmlmin` | `minify-html` PyO3 wheels | Strong candidate; adds a compiled dependency and needs template/hydration regression fixtures |
| CSS minify | `cssmin` | Lightning CSS CLI or `rcssmin` | Node/binary dependency; current output is adequate and tested |
| JS minify | `rjsmin` with nested-template guard | esbuild/oxc/Terser subprocess | Requires Node/binary; preserve current safe fallback |
| SVG | none | SVGO CLI or Scour | No user request yet; validate reference-heavy SVGs first |
| Images | Pillow WebP | Pillow AVIF + `<picture>`/srcset | AVIF encoding cost and browser fallback complexity |
| Fingerprinting | SHA-256 rename + regex rewrite | Manifest + dependency-ordered hashing | Existing behavior covers the common static-site case |
| Compression | Brotli/gzip sidecars | Verify serving, measure compressed transfer | Already implemented; add validation, not a new engine |
| Reporting | terminal totals | JSON report + per-file records | Implemented in this milestone |

## 4. Technical limitations

- Regex-based reference rewriting cannot see URLs built at runtime, template expressions, or every modern JS import form.
- Hashing can legitimately increase total output bytes when an absolute URL (for example `og:image`) forces both the original and hashed copies to ship.
- Pure-Python JS minification is token-level only; it cannot match AST-based minifiers.
- `htmlmin` imports the deprecated `cgi` module; Python 3.13 removal will require replacing or pinning it.
- Inlining small images trades request count for bytes; the existing `--inline-small` option does not prove a net payload win on every page.
- A browser is required for true visual/critical-CSS validation; byte checks alone cannot prove a site still renders correctly.

## 5. Licensing considerations

- Safe to depend on: MIT (minify-html, esbuild, SVGO, cssnano, oxc), Apache-2.0 (rjsmin, Sharp, Pillow-compatible terms), BSD-2-Clause (Terser).
- MPL-2.0 Lightning CSS: file-level copyleft; depending on it is fine, modifying its files triggers source obligations.
- Avoid bundling GPL-family image binaries (pngquant, gifsicle) without a deliberate licensing decision.
- Do not copy code from proprietary tools. Reimplement behavior from documented interfaces and verify with tests.

## 6. Features WebTimize should adopt

1. **JSON build reports** with counts, byte sizes, transformations, warnings, errors, and timing. Implemented.
2. **Staged output** so a failed build cannot replace a working deployment. Implemented.
3. **Sidecar validation** by decompressing every generated `.gz`/`.br` and comparing bytes. Implemented.
4. **Deterministic output** where practical (gzip mtime=0 already; sorted traversal).
5. **License-comment preservation** in a future JS minifier.
6. **Manifest output** for hashed assets, so frameworks and CDNs can consume the mapping.
7. **Opt-in aggressive transforms** with explicit compatibility warnings.

## 7. Features WebTimize should avoid duplicating

- General-purpose bundling, tree-shaking, code splitting (Parcel/Vite/Rolldown own this).
- Runtime image resizing or framework-specific image loaders (Sharp/Next own this).
- Lighthouse scoring or full performance audits.
- Critical-CSS extraction in the first release; it requires a browser or a new dependency.
- Backend application rewriting (Python/PHP/Node execution semantics differ).
- A local proxy or arbitrary response-body rewriting.

## 8. Identified opportunities

- **Post-build, framework-agnostic optimization** of `_site/`, `dist/`, or `public/` for SSGs and hand-written sites.
- **Safe-by-default reporting**: tell users exactly what changed, what was skipped, and what could not be verified.
- **Dependency-ordered hashing + manifest**: images/fonts → CSS `url()` → CSS/JS → HTML references, with an emitted manifest.
- **Python-centric CI fit**: `pipx install`, no Node or Chrome required for the default path.
- **Explicit compatibility diagnostics**: warnings for dynamic references, absolute-URL duplicates, non-UTF-8 files, and unsupported JS.

## 9. Recommended development priorities

1. Finish report/safety/validation coverage and document the report schema. (This milestone.)
2. Add a realistic fixture site and run the full pipeline in CI; compare output bytes and sidecar integrity.
3. Evaluate `minify-html` behind an optional backend, with hydration/template fixtures.
4. Add a manifest for hashed assets and document how to consume it.
5. Evaluate AVIF as opt-in with `<picture>` fallback, only after image compatibility tests.
6. Consider critical CSS and font subsetting only when a concrete user workflow justifies the dependency cost.

## 10. Sources

All accessed 2026-10-30.

- https://developer.chrome.com/docs/lighthouse/overview
- https://github.com/GoogleChrome/lighthouse
- https://github.com/GoogleChrome/lighthouse-ci
- https://unlighthouse.dev/
- https://www.webpagetest.org/about
- https://parceljs.org/features/production/
- https://vite.dev/guide/build.html
- https://nextjs.org/docs/app/api-reference/components/image
- https://gohugo.io/functions/resources/minify/
- https://github.com/digitalsparky/jekyll-minifier
- https://github.com/terser/html-minifier-terser
- https://github.com/wilsonzlin/minify-html
- https://github.com/ndparker/rjsmin
- https://github.com/terser/terser
- https://esbuild.github.io/api/
- https://github.com/oxc-project/oxc
- https://lightningcss.dev/
- https://github.com/cssnano/cssnano
- https://github.com/svg/svgo
- https://sharp.pixelplumbing.com/
- https://pillow.readthedocs.io/en/stable/releasenotes/11.3.0.html
- https://github.com/imagemin/imagemin
- https://github.com/addyosmani/critical
- https://docs.djangoproject.com/en/5.2/ref/contrib/staticfiles/
- https://github.com/privatenumber/minification-benchmarks
