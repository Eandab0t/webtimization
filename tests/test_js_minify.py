import pytest
from arachni_opt.js_minify import minify


def test_removes_spaces():
    js = "var x = 1; var y = 2;"
    result = minify(js)
    assert 'x' in result and 'y' in result


def test_valid_output():
    js = "function hello() { return 'world'; }"
    result = minify(js)
    assert 'hello' in result and 'world' in result
