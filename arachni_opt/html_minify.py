import htmlmin

_MINIFIER = htmlmin.Minifier()

def minify(html: str, remove_optional_closing_tags: bool = True) -> str:
    return _MINIFIER.minify(html, remove_optional_closing_tags=remove_optional_closing_tags)
