"""Asserts the Python and TypeScript channel enums stay in lockstep.

``useChannel`` filters messages on exact string match
(``message.resource === resource``), so a one-character drift between
``config/enums.py`` and ``app/javascript/types/channels.ts`` is silently
swallowed at runtime. This test catches the drift at CI time instead.
"""

import re
from pathlib import Path

from config.enums import ChannelEventAction, ChannelEventResource

TS_PATH = Path(__file__).resolve().parents[3] / "app" / "javascript" / "types" / "channels.ts"

_ENUM_BODY_PATTERN = re.compile(r"export enum (\w+)\s*\{([^}]*)\}", re.MULTILINE)
_MEMBER_PATTERN = re.compile(r'^\s*\w+\s*=\s*"([^"]+)"', re.MULTILINE)


def _parse_ts_enum(name: str) -> set[str]:
    source = TS_PATH.read_text()
    for enum_name, body in _ENUM_BODY_PATTERN.findall(source):
        if enum_name == name:
            return set(_MEMBER_PATTERN.findall(body))
    raise AssertionError(f"Could not find enum {name} in {TS_PATH}")


def test_channel_event_resource_strings_match():
    python_values = {member.value for member in ChannelEventResource}
    typescript_values = _parse_ts_enum("ChannelEventResource")
    assert python_values == typescript_values


def test_channel_event_action_strings_match():
    python_values = {member.value for member in ChannelEventAction}
    typescript_values = _parse_ts_enum("ChannelEventAction")
    assert python_values == typescript_values
