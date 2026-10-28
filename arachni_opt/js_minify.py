import jsmin

def minify(js: str) -> str:
    return jsmin.jsmin(js)
