from webtim.css_minify import minify


def test_removes_spaces():
    result = minify("body { color: red; }")
    assert "body" in result and "red" in result and "  " not in result


def test_preserves_rules():
    assert "768" in minify("@media (min-width: 768px) { .a { display: block; } }")
