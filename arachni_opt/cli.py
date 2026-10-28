import os
from pathlib import Path

import click

from arachni_opt.html_minify import minify as minify_html
from arachni_opt.css_minify import minify as minify_css
from arachni_opt.js_minify import minify as minify_js

EXTENSIONS = {'.html': 'html', '.css': 'css', '.js': 'js'}


def _minify(text: str, kind: str) -> str:
    if kind == 'html':
        return minify_html(text)
    if kind == 'css':
        return minify_css(text)
    if kind == 'js':
        return minify_js(text)
    return text


@click.command()
@click.argument('input', type=click.Path(exists=True, dir_okay=True, file_okay=True))
@click.option('-o', '--output', 'output_dir', default=None, type=click.Path())
@click.option('--dry-run', is_flag=True, help='Preview without writing')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def main(input, output_dir, dry_run, verbose):
    input_path = Path(input).resolve()

    if not dry_run:
        out = (Path(output_dir) if output_dir else Path(str(input_path) + '_optimized')).resolve()
        out.mkdir(parents=True, exist_ok=True)
    else:
        out = None

    targets = []
    if input_path.is_file():
        ext = input_path.suffix.lower()
        if ext in EXTENSIONS:
            targets.append(input_path)
        else:
            click.echo(f"Skipping {input_path.name}: no optimizer for '{ext}'")
            return
    elif input_path.is_dir():
        for root, _, files in os.walk(input_path):
            for fname in sorted(files):
                ext = Path(fname).suffix.lower()
                if ext in EXTENSIONS:
                    targets.append(Path(root) / fname)

    if not targets:
        click.echo(f"No HTML/CSS/JS files found in {input_path}")
        return

    total_original = 0
    total_minified = 0
    total_gz = 0
    total_br = 0

    for target in targets:
        ext = target.suffix.lower()
        kind = EXTENSIONS[ext]
        raw = target.read_text(encoding='utf-8')
        original_size = len(raw.encode('utf-8'))

        minified_raw = _minify(raw, kind)
        minified_bytes = minified_raw.encode('utf-8')
        minified_size = len(minified_bytes)

        if out is not None:
            import brotli, gzip
            name = target.name
            (out / name).write_bytes(minified_bytes)
            (out / (name + '.gz')).write_bytes(gzip.compress(minified_bytes))
            (out / (name + '.br')).write_bytes(brotli.compress(minified_bytes))

        total_original += original_size
        total_minified += minified_size
        total_gz += len(gzip.compress(minified_bytes))
        total_br += len(brotli.compress(minified_bytes))

        if verbose:
            savings_pct = (1 - minified_size / original_size) * 100
            click.echo(
                f"  {target.relative_to(input_path)}  "
                f"{original_size:>7d} -> {minified_size:>7d} ({savings_pct:.1f}%)"
            )

    savings = (1 - total_minified / total_original) * 100 if total_original else 0
    click.echo()
    click.secho(f"Totals:", bold=True)
    click.echo(f"  Original:   {total_original:>8d} bytes")
    click.echo(f"  Minified:   {total_minified:>8d} bytes ({savings:.1f}% saved)")
    click.echo(f"  Gzip size:  {total_gz:>8d} bytes (precompressed)")
    click.echo(f"  Brotli size:{total_br:>8d} bytes (precompressed)")
    if out is not None:
        click.echo(f"  Output dir: {out}")


if __name__ == '__main__':
    main()
