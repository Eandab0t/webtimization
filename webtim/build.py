"""Build a static site: discover, optimize, validate, and publish atomically."""
from __future__ import annotations

import gzip
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import brotli

from webtim import __version__
from webtim.compress import compress
from webtim.css_minify import minify as minify_css
from webtim.html_minify import minify as minify_html
from webtim.js_minify import minify as minify_js
from webtim.serve_config import caddy, nginx
from webtim import transforms as T

MINIFIERS = {".html": minify_html, ".css": minify_css, ".js": minify_js}
COMPRESSIBLE = {".html", ".css", ".js", ".svg", ".json", ".xml", ".txt"}
SKIP_DIRS = {"node_modules"}


class BuildError(RuntimeError):
    """A build that must stop without replacing the published output."""


def collect(input_path: Path, exclude: Path | None = None) -> dict:
    """Read the input into {relative PurePosixPath: bytes}, skipping hidden dirs and `exclude`."""
    if input_path.is_file():
        return {PurePosixPath(input_path.name): input_path.read_bytes()}
    files = {}
    for root, dirs, names in os.walk(input_path):
        dirs[:] = [
            d for d in sorted(dirs)
            if not d.startswith(".") and d not in SKIP_DIRS
            and (exclude is None or (Path(root) / d).resolve() != exclude)
        ]
        for name in sorted(names):
            path = Path(root) / name
            files[PurePosixPath(path.relative_to(input_path).as_posix())] = path.read_bytes()
    return files


def optimize(
    files: dict,
    *,
    webp: bool = False,
    inline: int = 0,
    defer: bool = False,
    hash_names: bool = False,
    warn=lambda message: None,
    stats: dict | None = None,
) -> dict:
    """Run the pipeline on {path: bytes} and return the optimized {path: bytes}."""
    stats = stats if stats is not None else {}
    stats.setdefault("minified", [])
    stats.setdefault("minified_unchanged", [])
    stats.setdefault("skipped", [])
    stats.setdefault("failed", [])
    stats.setdefault("webp", {})
    stats.setdefault("inlined", 0)
    stats.setdefault("dropped", [])
    stats.setdefault("hashed", {})
    stats.setdefault("hash_skipped", {})
    stats.setdefault("deferred", 0)

    site, undecodable = {}, {}
    for path, data in files.items():
        if path.suffix in MINIFIERS:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                warn(f"{path}: not UTF-8, copied unchanged")
                stats["skipped"].append(str(path))
                undecodable[path] = data
                continue
        site[path] = data

    def minify(path, minifier) -> None:
        before = site[path]
        try:
            site[path] = minifier(before.decode("utf-8")).encode("utf-8")
        except Exception as exc:  # a minifier choking must never lose the original file
            warn(f"{path}: minify failed ({exc}), copied unchanged")
            stats["failed"].append(str(path))
            return
        bucket = "minified" if site[path] != before else "minified_unchanged"
        stats[bucket].append(str(path))

    for path in [p for p in site if p.suffix in {".css", ".js"}]:
        minify(path, MINIFIERS[path.suffix])

    if webp:
        skipped_webp: dict = {}
        stats["webp"] = {str(old): str(new) for old, new in T.to_webp(site, skipped=skipped_webp).items()}
        stats["webp_skipped"] = skipped_webp
        for reason in skipped_webp.values():
            warn(reason)
    if inline:
        dropped = []
        stats["inlined"] = T.inline_small(site, inline, dropped=dropped)
        stats["dropped"].extend(str(path) for path in dropped)
    if hash_names:
        skipped_hash: dict = {}
        stats["hashed"] = {
            str(old): str(new) for old, new in T.hash_names(site, skipped=skipped_hash).items()
        }
        stats["hash_skipped"] = skipped_hash
        for reason in skipped_hash.values():
            warn(reason)
    if defer:
        stats["deferred"] = T.defer_scripts(site)

    for path in [p for p in site if p.suffix == ".html"]:
        minify(path, minify_html)
    return {**site, **undecodable}


def _measure(site: dict) -> tuple[list[dict], dict]:
    """Return report records and the generated sidecar bytes for each output file."""
    records, payloads = [], {}
    for path, data in sorted(site.items()):
        gzip_bytes, brotli_bytes = b"", b""
        if path.suffix in COMPRESSIBLE:
            gzip_bytes, brotli_bytes = compress(data)
        if len(gzip_bytes) >= len(data):
            gzip_bytes = b""
        if len(brotli_bytes) >= len(data):
            brotli_bytes = b""
        payloads[path] = (gzip_bytes, brotli_bytes)
        records.append({
            "path": str(path),
            "bytes": len(data),
            "gzip_bytes": len(gzip_bytes),
            "brotli_bytes": len(brotli_bytes),
        })
    return records, payloads


def _write_site(site: dict, payloads: dict, destination: Path, verbose=None) -> None:
    for path, data in sorted(site.items()):
        gzip_bytes, brotli_bytes = payloads[path]
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if gzip_bytes:
            target.with_name(target.name + ".gz").write_bytes(gzip_bytes)
        if brotli_bytes:
            target.with_name(target.name + ".br").write_bytes(brotli_bytes)
        if verbose:
            verbose(
                f"  {path}  {len(data):>8d} B  "
                f"gz {len(gzip_bytes) or '-':>6}  br {len(brotli_bytes) or '-':>6}"
            )


def validate_sidecars(destination: Path, site: dict) -> list[str]:
    """Confirm every generated sidecar decompresses back to its source bytes."""
    errors = []
    for path, data in sorted(site.items()):
        target = destination / path
        for suffix, decompress in ((".gz", gzip.decompress), (".br", brotli.decompress)):
            sidecar = target.with_name(target.name + suffix)
            if not sidecar.exists():
                continue
            try:
                if decompress(sidecar.read_bytes()) != data:
                    errors.append(f"{path}{suffix}: content mismatch")
            except Exception as exc:
                errors.append(f"{path}{suffix}: cannot decompress ({exc})")
    return errors


def _promote(staging: Path, output: Path) -> None:
    """Replace the output directory only after the staging build is complete."""
    backup = None
    if output.exists():
        backup = output.with_name(f".{output.name}.backup")
        if backup.exists():
            shutil.rmtree(backup)
        output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        if backup is not None:
            backup.rename(output)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def _pct(original: int, final: int) -> float:
    return round((1 - final / original) * 100, 1) if original else 0.0


def build(
    input_path: Path | str,
    output_path: Path | str,
    *,
    webp: bool = False,
    inline: int = 0,
    defer: bool = False,
    hash_names: bool = False,
    emit_config: str | None = None,
    dry_run: bool = False,
    verbose=None,
    warn=lambda message: None,
) -> dict:
    """Build a site and return a machine-readable report."""
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    source = Path(input_path).resolve()
    output = Path(output_path).resolve()
    warnings: list[str] = []

    def record_warning(message: str) -> None:
        if message not in warnings:
            warnings.append(message)
            warn(message)

    if output == source or output in source.parents:
        raise BuildError("output must not be the input directory or contain it")
    if output.exists() and not output.is_dir():
        raise BuildError(f"output exists and is not a directory: {output}")
    if emit_config not in (None, "nginx", "caddy"):
        raise BuildError(f"unknown server config: {emit_config}")

    files = collect(source, exclude=output)
    report = {
        "schema_version": 1,
        "tool": {"name": "webtim", "version": __version__},
        "input": str(source),
        "output": str(output),
        "dry_run": dry_run,
        "sizes_are_estimated": dry_run,
        "started_at": started_at,
        "status": "ok",
        "counts": {},
        "sizes": {},
        "transformations": {},
        "files": [],
        "warnings": warnings,
        "errors": [],
    }
    if not any(path.suffix in MINIFIERS for path in files):
        report["status"] = "no_web_files"
        report["duration_ms"] = round((time.perf_counter() - started) * 1000)
        return report

    stats: dict = {}
    site = optimize(
        files, webp=webp, inline=inline, defer=defer, hash_names=hash_names,
        warn=record_warning, stats=stats,
    )
    records, payloads = _measure(site)
    report["files"] = records
    report["transformations"] = {
        "minified": len(stats["minified"]),
        "minified_unchanged": len(stats["minified_unchanged"]),
        "webp": len(stats["webp"]),
        "webp_skipped": len(stats.get("webp_skipped", {})),
        "inlined": stats["inlined"],
        "hashed": len(stats["hashed"]),
        "hashed_skipped": len(stats["hash_skipped"]),
        "deferred": stats["deferred"],
        "dropped": len(stats["dropped"]),
    }
    original_bytes = sum(len(data) for data in files.values())
    output_bytes = sum(record["bytes"] for record in records)
    gzip_wire = sum(record["gzip_bytes"] or record["bytes"] for record in records)
    brotli_wire = sum(record["brotli_bytes"] or record["bytes"] for record in records)
    report["sizes"] = {
        "original_bytes": original_bytes,
        "output_bytes": output_bytes,
        "saved_bytes": original_bytes - output_bytes,
        "saved_percent": _pct(original_bytes, output_bytes),
        "gzip_wire_bytes": gzip_wire,
        "brotli_wire_bytes": brotli_wire,
    }
    report["counts"] = {
        "discovered": len(files),
        "processed": len(files) - len(stats["skipped"]),
        "skipped": len(stats["skipped"]),
        "failed": len(stats["failed"]),
        "output_files": len(site),
    }
    if stats["failed"]:
        report["status"] = "partial"

    if dry_run:
        report["duration_ms"] = round((time.perf_counter() - started) * 1000)
        return report

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and any(output.iterdir()):
        record_warning(f"{output} is not empty; it will be replaced after a successful build")
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=str(output.parent)))
    config_temp = None
    try:
        _write_site(site, payloads, staging, verbose)
        errors = validate_sidecars(staging, site)
        if errors:
            raise BuildError("; ".join(errors))
        if emit_config:
            config_temp = output.parent / f".{output.name}.{emit_config}.conf.tmp"
            config_temp.write_text((nginx if emit_config == "nginx" else caddy)(str(output)), encoding="utf-8")
        _promote(staging, output)
        staging = None
        if config_temp:
            config_temp.replace(output.parent / f"{output.name}.{emit_config}.conf")
            report["config"] = str(output.parent / f"{output.name}.{emit_config}.conf")
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError(str(exc)) from exc
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if config_temp is not None and config_temp.exists():
            config_temp.unlink()
    report["duration_ms"] = round((time.perf_counter() - started) * 1000)
    return report
