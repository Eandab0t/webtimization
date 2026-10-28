import pytest
from arachni_opt.css_minify import minify


def test_removes_spaces():
    css = "body { color: red; }"
    result = minify(css)
    assert 'body' in result and 'red' in result


def test_preserves_rules():
    css = "@media (min-width: 768px) { .a { display: block; } }"
    result = minify(css)
    assert '768' in result
