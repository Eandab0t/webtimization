from webtim.html_minify import minify


def test_removes_comments():
    result = minify("<!-- hello --> <div>hello</div>")
    assert "hello" in result
    assert "<!--" not in result


def test_collapse_whitespace():
    result = minify("<div>  hello   world  </div>")
    assert "hello world" in result
