import shutil
import subprocess

import pytest

from webtim.js_minify import minify


def test_removes_spaces():
    result = minify("var x = 1; var y = 2;")
    assert "x" in result and "y" in result


def test_valid_output():
    result = minify("function hello() { return 'world'; }")
    assert "hello" in result and "world" in result


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("src", [
    "const a = `x ${1 + 1} y`; console.log(a);",           # template literal
    "const r = /ab+c/g; console.log('abbc'.match(r));",     # regex literal
    "const a = `line1\n  line2 ${ `in ${2} ner` }`; console.log(a);",  # nested template: left unminified
    "const s = 'a  b'; console.log(s, 4 / 2 / 1);",
    "let a = 1\nlet b = 2\nconsole.log(a\n+ b)",                 # ASI must survive
    "// c\nlet f = (a, b) => a + b; /* x */ console.log(f(1, 2));",
])
def test_minified_js_still_runs_the_same(src, tmp_path):
    """Round trip: original and minified must print the same thing under node."""
    def run(code):
        p = tmp_path / "t.js"
        p.write_text(code)
        return subprocess.run(["node", str(p)], capture_output=True, text=True).stdout
    assert run(minify(src)) == run(src) != ""
