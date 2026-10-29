import importlib.util
import os
from pathlib import Path, PurePosixPath

import click

from webtim import __version__
from webtim import transforms as T
from webtim.compress import compress
from webtim.css_minify import minify as minify_css
from webtim.html_minify import minify as minify_html
from webtim.js_minify import minify as minify_js
from webtim.serve_config import caddy, nginx

MINIFIERS = {".html": minify_html, ".css": minify_css, ".js": minify_js}
# Text formats worth a .gz/.br sidecar; images and fonts are already compressed.
COMPRESSIBLE = {".html", ".css", ".js", ".svg", ".json", ".xml", ".txt"}
SKIP_DIRS = {"node_modules"}


def collect(input_path: Path, exclude: Path | None = None) -> dict:
    """Read the input into {relative PurePosixPath: bytes}, skipping hidden dirs and `exclude`."""
    if input_path.is_file():
        return {PurePosixPath(input_path.name): input_path.read_bytes()}
    files = {}
    for root, dirs, names in os.walk(input_path):
        dirs[:] = [d for d in sorted(dirs) if not d.startswith(".") and d not in SKIP_DIRS
                   and (exclude is None or (Path(root) / d).resolve() != exclude)]
        for name in sorted(names):
            p = Path(root) / name
            files[PurePosixPath(p.relative_to(input_path).as_posix())] = p.read_bytes()
    return files


def optimize(files: dict, *, webp=False, inline=0, defer=False, hash_names=False, warn=lambda m: None) -> dict:
    """Run the pipeline on {path: bytes} and return the optimized {path: bytes}.

    Order matters: css/js are minified first (hashes and inline sizes must see final bytes),
    HTML is minified last (the regexes in transforms.py expect the author's original markup).
    """
    site, undecodable = {}, {}
    for p, data in files.items():
        if p.suffix in MINIFIERS:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                warn(f"{p}: not UTF-8, copied unchanged")
                undecodable[p] = data
                continue
        site[p] = data

    for p in [p for p in site if p.suffix in {".css", ".js"}]:
        try:
            site[p] = MINIFIERS[p.suffix](site[p].decode("utf-8")).encode("utf-8")
        except Exception as e:  # a minifier choking must never lose the original file
            warn(f"{p}: minify failed ({e}), copied unchanged")

    if webp:
        T.to_webp(site)
    if inline:
        T.inline_small(site, inline)
    if hash_names:
        T.hash_names(site)
    if defer:
        T.defer_scripts(site)

    for p in [p for p in site if p.suffix == ".html"]:
        try:
            site[p] = minify_html(site[p].decode("utf-8")).encode("utf-8")
        except Exception as e:
            warn(f"{p}: minify failed ({e}), copied unchanged")
    return {**site, **undecodable}


def _pct(a: int, b: int) -> str:
    return f"{(1 - b / a) * 100:.1f}%" if a else "0.0%"


@click.command()
@click.version_option(__version__, prog_name="webtim")
@click.argument("input", type=click.Path(exists=True))
@click.option("-o", "--output", "output_dir", default=None, type=click.Path(),
              help="Output directory (default: <input>_optimized)")
@click.option("--dry-run", is_flag=True, help="Preview sizes without writing")
@click.option("-v", "--verbose", is_flag=True, help="Per-file sizes")
@click.option("--webp", is_flag=True, help="Convert PNG/JPEG to WebP when smaller (needs Pillow)")
@click.option("--inline-small", "inline", type=int, default=0, metavar="BYTES",
              help="Inline images up to BYTES as data: URIs (2048 is a sane start; 0 = off)")
@click.option("--defer-scripts", "defer", is_flag=True, help="Add defer to external scripts on pages with no inline code")
@click.option("--hash", "hash_names", is_flag=True, help="Rename assets to name.<hash>.ext for forever-caching")
@click.option("--emit-config", type=click.Choice(["nginx", "caddy"]),
              help="Write a server snippet next to the output dir (not inside it, so it isn't served)")
def main(input, output_dir, dry_run, verbose, webp, inline, defer, hash_names, emit_config):
    if webp and importlib.util.find_spec("PIL") is None:
        raise click.UsageError("--webp needs Pillow: pip install Pillow")
    src = Path(input).resolve()
    out = Path(output_dir).resolve() if output_dir else Path(str(src) + "_optimized")

    files = collect(src, exclude=out)
    if not any(p.suffix in MINIFIERS for p in files):
        click.echo(f"No HTML/CSS/JS files found in {src}")
        return
    site = optimize(files, webp=webp, inline=inline, defer=defer, hash_names=hash_names,
                    warn=lambda m: click.echo(f"warning: {m}", err=True))

    if not dry_run:
        if out.is_dir() and any(out.iterdir()):
            click.echo(f"note: {out} is not empty; files from earlier runs are not deleted", err=True)
        out.mkdir(parents=True, exist_ok=True)

    raw = gz_total = br_total = 0
    for p, data in sorted(site.items()):
        raw += len(data)
        gz, br = (b"", b"")
        if p.suffix in COMPRESSIBLE:
            gz, br = compress(data)
        # a sidecar bigger than the file would only cost bandwidth, so it is not written
        keep_gz, keep_br = (0 < len(gz) < len(data)), (0 < len(br) < len(data))
        gz_total += len(gz) if keep_gz else len(data)
        br_total += len(br) if keep_br else len(data)
        if not dry_run:
            dest = out / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if keep_gz:
                (dest.parent / (dest.name + ".gz")).write_bytes(gz)
            if keep_br:
                (dest.parent / (dest.name + ".br")).write_bytes(br)
        if verbose:
            click.echo(f"  {p}  {len(data):>8d} B  gz {len(gz) if keep_gz else '-':>6}  br {len(br) if keep_br else '-':>6}")

    original = sum(len(d) for d in files.values())
    click.echo()
    click.secho("Totals:", bold=True)
    click.echo(f"  Input:   {len(files):>4d} files {original:>9d} bytes")
    click.echo(f"  Output:  {len(site):>4d} files {raw:>9d} bytes ({_pct(original, raw)} saved)")
    click.echo(f"  Over the wire, gzip:   {gz_total:>9d} bytes ({_pct(original, gz_total)} vs input)")
    click.echo(f"  Over the wire, brotli: {br_total:>9d} bytes ({_pct(original, br_total)} vs input)")

    if not dry_run:
        click.echo(f"  Output dir: {out}")
        if emit_config:
            conf = out.parent / f"{out.name}.{emit_config}.conf"
            conf.write_text((nginx if emit_config == "nginx" else caddy)(str(out)), encoding="utf-8")
            click.echo(f"  Server config: {conf}")


if __name__ == "__main__":
    main()
