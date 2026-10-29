import re

import rjsmin

# A backtick inside ${ ... }: rjsmin (like jsmin) squeezes spaces in the nested template's text.
_NESTED_TEMPLATE = re.compile(r"\$\{[^}]*`")


def minify(js: str) -> str:
    # shortcut: regex guess at nested templates, swap in esbuild/terser if you need to minify those files too
    if _NESTED_TEMPLATE.search(js):
        return js
    return rjsmin.jsmin(js)
