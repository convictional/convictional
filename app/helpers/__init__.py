from collections.abc import Callable
from datetime import timedelta
from urllib.parse import quote

from jinja2 import Environment

from config import enums, settings
from lib.html import sanitize_email_html_content, strip_html

from .assets import asset_version_hash
from .channels import topic_id
from .datetimes import (
    default_snooze_times,
    format_date,
    format_datetime,
    now,
    today,
    tomorrow,
)
from .goals import GoalStatusMap
from .hotkeys import format_kbd_hint
from .json import to_json
from .markdown import render_markdown, with_markdown_format_citations
from .react import react_mode_enabled
from .strings import (
    convert_none_to_string,
    format_page_title,
    format_sharing,
    linebreaksbr,
    og_description,
    pluralize,
    snake_case,
    titleize,
)
from .url import (
    absolute_url,
    current_route,
    path_for_static_file,
    url_for_bundled_file,
    url_for_content,
    url_for_static_file,
    url_with_fragment,
)
from .users import user_avatar_url
from .workspaces import resource_icon, resource_label

__all__ = ["add_helpers_to_env"]

_DEV_FAVICON_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<path fill="{color}" d="M25.03,18.22l-.8-1.38c-1.06-1.85-3.45-2.48-5.29-1.42l-.28.16'
    "c-.76.44-1.74.18-2.17-.58h0c-.44-.76-.18-1.74.58-2.17l.45-.26c1.76-1.02,2.37-3.27,"
    '1.35-5.03l-.8-1.38h13.93s-6.97,12.07-6.97,12.07Z"/>'
    '<path fill="{color}" d="M8.93,26.34c-3.06,1.76-7.03.52-8.48-2.8-1.07-2.45-.08-5.84,'
    "2.14-7.34,1.8-1.21,3.98-1.31,5.79-.51,1.14.51,2.94.44,4.02-.18l.41-.24c.76-.44,"
    "1.73-.18,2.16.58h0c.44.76.18,1.73-.58,2.16l-.4.23c-1.04.6-2.01,2.06-2.08,3.26"
    '-.12,1.94-1.17,3.79-2.98,4.83Z"/>'
    "</svg>"
)


def dev_favicon_svg() -> str:
    svg = _DEV_FAVICON_SVG_TEMPLATE.format(color=settings.dev_color)
    return quote(svg, safe="")


def add_helpers_to_env(env: Environment, globals: dict[str, Callable] = {}):
    env.filters["format_datetime"] = format_datetime
    env.filters["format_date"] = format_date
    env.filters["linebreaksbr"] = linebreaksbr
    env.filters["markdown"] = render_markdown
    env.filters["with_markdown_format_citations"] = with_markdown_format_citations
    env.filters["strip_html"] = strip_html
    env.filters["sanitize_email_html_content"] = sanitize_email_html_content
    env.filters["format_page_title"] = format_page_title
    env.filters["format_sharing"] = format_sharing
    env.filters["tojson"] = to_json
    env.filters["titleize"] = titleize
    env.filters["og_description"] = og_description

    env.globals["settings"] = settings
    env.globals["url_for_static_file"] = url_for_static_file
    env.globals["path_for_static_file"] = path_for_static_file
    env.globals["url_for_bundled_file"] = url_for_bundled_file
    env.globals["current_route"] = current_route
    env.globals["react_mode_enabled"] = react_mode_enabled
    env.globals["url_with_fragment"] = url_with_fragment
    env.globals["format_datetime"] = format_datetime
    env.globals["format_date"] = format_date
    env.globals["now"] = now
    env.globals["today"] = today
    env.globals["tomorrow"] = tomorrow
    env.globals["timedelta"] = timedelta
    env.globals["default_snooze_times"] = default_snooze_times
    env.globals["pluralize"] = pluralize
    env.globals["titleize"] = titleize
    env.globals["snake_case"] = snake_case
    env.globals["url_for_content"] = url_for_content
    env.globals["enums"] = enums
    env.globals["resource_icon"] = resource_icon
    env.globals["resource_label"] = resource_label
    env.globals["get_goal_status_map"] = GoalStatusMap.get_status_map
    env.globals["get_goal_status_object"] = GoalStatusMap.get_status_object
    env.globals["topic_id"] = topic_id
    env.globals["absolute_url"] = absolute_url
    env.globals["asset_version_hash"] = asset_version_hash
    env.globals["format_kbd_hint"] = format_kbd_hint
    env.globals["dev_favicon_svg"] = dev_favicon_svg
    env.globals["user_avatar_url"] = user_avatar_url
    for name, func in globals.items():
        env.globals[name] = func

    env.finalize = convert_none_to_string
