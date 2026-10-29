"""Server snippets that serve the .br/.gz sidecars and set cache headers for hashed files."""
from webtim.transforms import HASHED_RE

LONG = "public, max-age=31536000, immutable"  # fingerprinted files never change under the same URL


def nginx(root: str) -> str:
    return f"""# Include inside a server {{ }} block.
root {root};
gzip_static on;
gzip_vary on;
# brotli_static needs the ngx_brotli module; uncomment only if `nginx -V` lists it.
# brotli_static on;

# Hashed assets (name.<hash>.ext): cache for a year, never revalidate.
location ~* "{HASHED_RE}" {{
    add_header Cache-Control "{LONG}";
}}

# Everything else: always revalidate (ETag), so HTML updates show up immediately.
location / {{
    add_header Cache-Control "no-cache";
}}
"""


def caddy(root: str) -> str:
    return f"""# Caddyfile site block body. Caddy serves name.br / name.gz when the client accepts them.
root * {root}
@hashed path_regexp hashed {HASHED_RE}
header @hashed Cache-Control "{LONG}"
header ?Cache-Control "no-cache"
file_server {{
    precompressed br gzip
}}
"""
