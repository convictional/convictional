from contextvars import ContextVar
from weakref import ReferenceType, ref

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound, pass_context
from markupsafe import Markup

template_variant: ContextVar[str | None] = ContextVar("template_variant", default=None)


@pass_context
def csrf_field(context) -> Markup:
    token = context.get("csrf_token") or ""
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


def add_macros_to_env(env: Environment):
    macros: Template = env.get_template("shared/macros.html.jinja")
    env.globals["csrf_field"] = csrf_field
    env.globals["submit_button"] = macros.module.__dict__["submit_button"]
    env.globals["form_shortcut_keybindings"] = macros.module.__dict__["form_shortcut_keybindings"]
    env.globals["render_breadcrumbs"] = macros.module.__dict__["render_breadcrumbs"]
    env.globals["empty"] = macros.module.__dict__["empty"]
    env.globals["tooltip"] = macros.module.__dict__["tooltip"]
    env.globals["dialog"] = macros.module.__dict__["dialog"]
    env.globals["test_id"] = macros.module.__dict__["test_id"]


class VariantAwareEnvironment(Environment):
    """
    Jinja Environment that makes template cache variant-aware to prevent cache collisions that cause incorrect template
    variants to be served.
    """

    def get_template(self, name, parent=None, globals=None):
        if isinstance(name, Template):
            return name

        if parent is not None:
            name = self.join_path(name, parent)

        return self._load_template_with_variant(name, globals)

    def _load_template_with_variant(self, name: str, globals):
        if self.loader is None:
            raise TypeError("no loader for this environment specified")

        variant = template_variant.get()
        cache_key_str = f"{name}#{variant}" if variant else name
        cache_key = (ref(self.loader), cache_key_str)

        if self.cache is not None:
            template = self.cache.get(cache_key)
            if template is not None and (not self.auto_reload or template.is_up_to_date):
                if globals:
                    template.globals.update(globals)
                return template

        template = self.loader.load(self, name, self.make_globals(globals))

        if self.cache is not None:
            self.cache[cache_key] = template

        return template


class VariantLoader(FileSystemLoader):
    """A jinja loader that implements template variants for mobile/desktop etc. similar to Rails view variants."""

    def get_source(self, environment: Environment, template: str):
        variant = template_variant.get()

        if variant:
            variant_template = self._build_variant_template_name(template, variant)

            try:
                return super().get_source(environment, variant_template)
            except TemplateNotFound:
                pass

        return super().get_source(environment, template)

    def _build_variant_template_name(self, template: str, variant: str) -> str:
        if not variant:
            return template

        if "." not in template:
            return f"{template}.{variant}"

        parts = template.split(".", 1)
        return f"{parts[0]}.{variant}.{parts[1]}"
