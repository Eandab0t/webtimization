"""Stdlib static server for small panels: serves .br/.gz sidecars and sets cache headers.

    webtim-serve OUTPUT_DIR [--port 8000]          # or: python -m webtim.serve

Meant for local/small deployments. For production traffic prefer nginx or Caddy (see serve_config.py).
"""
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import click

from webtim import __version__
from webtim.serve_config import LONG
from webtim.transforms import HASHED_RE


class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path) and self.path.split("?")[0].endswith("/"):
            path = os.path.join(path, "index.html")
        accepts = self.headers.get("Accept-Encoding", "")
        for enc, ext in (("br", ".br"), ("gzip", ".gz")):
            if os.path.isfile(path) and enc in accepts and os.path.isfile(path + ext):
                f = open(path + ext, "rb")
                self.send_response(200)
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Content-Length", str(os.fstat(f.fileno()).st_size))
                self.send_header("Content-Encoding", enc)
                self.end_headers()
                return f
        return super().send_head()

    def end_headers(self):
        self.send_header("Vary", "Accept-Encoding")
        hashed = re.search(HASHED_RE, self.path.split("?")[0])
        self.send_header("Cache-Control", LONG if hashed else "no-cache")
        super().end_headers()


@click.command()
@click.version_option(__version__, prog_name="webtim-serve")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--port", default=8000, show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
def main(directory, port, host):
    click.echo(f"Serving {directory} on http://{host}:{port}")
    ThreadingHTTPServer((host, port), partial(Handler, directory=directory)).serve_forever()


if __name__ == "__main__":
    main()
