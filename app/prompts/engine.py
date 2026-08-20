import re
from typing import Any

import jinja2

from app.models.accounts import Organization, User
from app.models.workspaces.goals import Goal
from lib.strings import escape_jinja

prompt_templates = None


def register_prompt_templates(env: jinja2.Environment):
    global prompt_templates
    prompt_templates = env


def build_prompt(template: str, override: str | None = None, **kwargs) -> str:
    if not prompt_templates:
        raise ValueError("Prompt templates have not been registered")

    if override:
        template_obj = prompt_templates.from_string(override)
        rendered = template_obj.render(**kwargs)
    else:
        rendered = prompt_templates.get_template(template).render(**kwargs)

    cleaned = _clean_template(rendered)
    return cleaned


async def organization_context(organization: Organization) -> dict[str, Any]:
    goals = await Goal.filter(Goal.filters.by_organization(organization.id) & Goal.filters.open).prefetch_related(
        "subgoals"
    )
    return {"organization": organization, "goals": goals}


async def current_user_context(user: User) -> dict[str, Any]:
    return {"current_user": user, **await organization_context(user.organization)}


def _clean_template(text: str) -> str:
    # Remove whitespace from the beginning of each line
    cleaned = "\n".join(line.strip() for line in text.split("\n"))

    # Strip base64 encoded images from text to prevent blowing token limits
    cleaned = _strip_base64_images(cleaned)

    # Remove any more than two consecutive newlines
    sanitized_newlines = re.sub(r"\n{3,}", "\n\n", cleaned)

    # remove leading & trailing newline characters these are caused by macros without whitespace removal
    stripped = sanitized_newlines.strip("\n")

    # Escape Jinja template syntax that may be in user input to prevent instructor from processing it
    return escape_jinja(stripped)


def _strip_base64_images(text: str) -> str:
    # Pattern to match data URIs for images with base64 encoding
    # Matches: data:image/<format>;base64,<base64-data>
    data_uri_pattern = r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+"

    # Pattern to match markdown images with data URIs
    # Matches: ![alt](data:image/format;base64,data)
    markdown_image_pattern = r"!\[[^\]]*\]\(data:image/[^;]+;base64,[A-Za-z0-9+/=]+\)"

    # Pattern to match HTML img tags with data URIs
    # Matches: <img src="data:image/format;base64,data" ...>
    html_img_pattern = r'<img[^>]*src=["\']data:image/[^;]+;base64,[A-Za-z0-9+/=]+["\'][^>]*>'

    # Remove all patterns
    text = re.sub(markdown_image_pattern, "", text)
    text = re.sub(html_img_pattern, "", text)
    text = re.sub(data_uri_pattern, "", text)

    return text
