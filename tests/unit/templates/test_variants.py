import tempfile
from pathlib import Path

from app.templates import VariantAwareEnvironment, VariantLoader, template_variant


def test_variant_loader_selects_mobile_variant():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        (tmp_path / "test_template.html.jinja").write_text("base content")
        (tmp_path / "test_template.mobile.html.jinja").write_text("mobile content")

        env = VariantAwareEnvironment(loader=VariantLoader(searchpath=tmp_path))

        template_variant.set("mobile")
        template = env.get_template("test_template.html.jinja")
        assert template.render() == "mobile content"

        template_variant.set(None)
        template = env.get_template("test_template.html.jinja")
        assert template.render() == "base content"

        template_variant.set("desktop")
        template = env.get_template("test_template.html.jinja")
        assert template.render() == "base content"


def test_variant_loader_falls_back_when_variant_missing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        (tmp_path / "test_template.html.jinja").write_text("base content")

        env = VariantAwareEnvironment(loader=VariantLoader(searchpath=tmp_path))

        template_variant.set("mobile")
        template = env.get_template("test_template.html.jinja")
        assert template.render() == "base content"


def test_variant_cache_isolation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        (tmp_path / "test_template.html.jinja").write_text("base content")
        (tmp_path / "test_template.mobile.html.jinja").write_text("mobile content")

        env = VariantAwareEnvironment(loader=VariantLoader(searchpath=tmp_path))

        template_variant.set(None)
        base_template = env.get_template("test_template.html.jinja")
        assert base_template.render() == "base content"

        template_variant.set("mobile")
        mobile_template = env.get_template("test_template.html.jinja")
        assert mobile_template.render() == "mobile content"

        template_variant.set(None)
        base_template_again = env.get_template("test_template.html.jinja")
        assert base_template_again.render() == "base content"

        assert base_template is base_template_again
        assert base_template is not mobile_template
