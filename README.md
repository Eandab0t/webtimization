# Webtimization

Offline web-page optimizer. Minifies HTML/CSS/JS and generates gzip/Brotli
precompressed sidecar files — all without network access.

## Quick Start

    pip install -e .
    arachni-opt path/to/index.html --verbose
    arachni-opt path/to/site/ -o output/ --verbose

## CLI

    arachni-opt <input> [OPTIONS]

    Inputs can be a single file or a directory (all .html/.css/.js are processed).

    Options:
      -o, --output PATH   Output directory (default: <input>_optimized)
      --dry-run           Preview without writing
      -v, --verbose       Per-file stats
      -h, --help          Show this help

## Compression

For each optimized file, sidecar files are written alongside the minified version:

  index.html        – minified HTML (UTF-8)
  index.html.gz     – gzip precompressed
  index.html.br     – brotli precompressed

Use Brotli for best compression ratio. Serve with a server that supports Content-Encoding negotiation.

## Design

Based on Arachnidium architecture concepts (in-transit optimization pipeline),
ported as a standalone offline CLI tool. No proxy, no Docker, no Node.js required.

    ponytail: hardcoded max — only one client today, parameterize when second client signs
