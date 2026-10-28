import cssmin

def minify(css: str) -> str:
    return cssmin.cssmin(css)
