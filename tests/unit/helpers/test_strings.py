from markupsafe import Markup

from app.helpers.strings import (
    linebreaksbr,
    make_plural,
    og_description,
    snake_case,
    titleize,
)


def test_titleize():
    assert titleize("") == ""
    assert titleize("hello world") == "Hello World"
    assert titleize("hello_world") == "Hello World"
    assert titleize("hello   world") == "Hello World"
    assert titleize("heLLo wORld") == "Hello World"
    assert titleize("hello") == "Hello"
    assert titleize("hello___world   example") == "Hello World Example"
    assert titleize("helloWorld") == "Hello World"
    assert titleize("HelloWorld") == "Hello World"
    assert titleize("helloWorldExample") == "Hello World Example"


def test_snake_case():
    assert snake_case("HelloWorld") == "hello_world"
    assert snake_case("helloWorld") == "hello_world"
    assert snake_case("helloWorldExample") == "hello_world_example"
    assert snake_case("hello") == "hello"
    assert snake_case("hello world") == "hello_world"


def test_make_plural():
    assert make_plural("child") == "children"
    assert make_plural("person") == "people"
    assert make_plural("bus") == "buses"
    assert make_plural("category") == "categories"
    assert make_plural("wolf") == "wolves"
    assert make_plural("photo") == "photos"


def test_linebreaksbr_basic():
    result = linebreaksbr("Hello\nWorld")
    assert result == "Hello<br>World"
    assert isinstance(result, Markup)


def test_linebreaksbr_escapes_html():
    result = linebreaksbr("Hello & goodbye\n<script>alert('xss')</script>")
    assert "&amp;" in result
    assert "&lt;script&gt;" in result
    assert "&lt;/script&gt;" in result
    assert "<br>" in result
    assert "<script>" not in result


def test_linebreaksbr_empty_string():
    result = linebreaksbr("")
    assert result == ""
    assert isinstance(result, Markup)


def test_linebreaksbr_none():
    result = linebreaksbr(None)
    assert result == ""
    assert isinstance(result, Markup)


def test_linebreaksbr_multiple_newlines():
    result = linebreaksbr("Line 1\nLine 2\nLine 3")
    assert result == "Line 1<br>Line 2<br>Line 3"


def test_linebreaksbr_special_chars():
    result = linebreaksbr('Test with <>&"\nNew line')
    assert "&lt;" in result
    assert "&gt;" in result
    assert "&amp;" in result
    assert "&#34;" in result or "&quot;" in result
    assert "<br>" in result


def test_og_description():
    assert og_description(None) == ""
    assert og_description("") == ""
    assert og_description("Hello world") == "Hello world"

    # Strips markdown links
    assert "](http" not in og_description("[Click here](http://example.com)")

    # Truncates long content
    long_text = "word " * 100
    result = og_description(long_text)
    assert len(result) <= 204
    assert result.endswith("...")
