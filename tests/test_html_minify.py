import pytest
from arachni_opt.html_minify import minify


def test_removes_comments():
    html = \"\"\"<!-- hello --> <div>hello</div>\"\"\"
    result = minify(html)
    assert 'hello' in result
    assert '<!--' not in result


def test_collapse_whitespace():
    html = \"<div>  hello   world  </div>\"
    result = minify(html)
    assert 'hello' in result and 'world' in result
