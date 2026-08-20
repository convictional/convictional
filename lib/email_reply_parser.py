"""
Email reply parser — extracts visible content from email bodies by stripping
quoted replies, signatures, and forwarded headers.

Adapted from https://github.com/zapier/email-reply-parser (MIT license).
Vendored locally to allow type annotations and avoid import mismatch with
the package's module layout.
"""

import re

SIG_REGEX = re.compile(r"(--|__|-\w)|(^Sent from my (\w+\s*){1,3})")
QUOTE_HDR_REGEX = re.compile(r"On.*wrote:$")
QUOTED_REGEX = re.compile(r"(>+)")
HEADER_REGEX = re.compile(r"^\*?(From|Sent|To|Subject):\*? .+")
_MULTI_QUOTE_HDR_REGEX = r"(?!On.*On\s.+?wrote:)(On\s(.+?)wrote:)"
MULTI_QUOTE_HDR_REGEX = re.compile(_MULTI_QUOTE_HDR_REGEX, re.DOTALL | re.MULTILINE)
MULTI_QUOTE_HDR_REGEX_MULTILINE = re.compile(_MULTI_QUOTE_HDR_REGEX, re.DOTALL)


class Fragment:
    def __init__(self, quoted: bool, first_line: str, *, headers: bool = False):
        self.signature = False
        self.headers = headers
        self.hidden = False
        self.quoted = quoted
        self._content: str | None = None
        self.lines = [first_line]

    def finish(self) -> None:
        self.lines.reverse()
        self._content = "\n".join(self.lines)
        self.lines = []

    @property
    def content(self) -> str:
        return (self._content or "").strip()


class EmailMessage:
    def __init__(self, text: str):
        self.fragments: list[Fragment] = []
        self.fragment: Fragment | None = None
        self.text = text.replace("\r\n", "\n")
        self.found_visible = False

    def read(self) -> "EmailMessage":
        self.found_visible = False

        # Collapse multi-line "On … wrote:" headers into a single line.
        is_multi_quote_header = MULTI_QUOTE_HDR_REGEX_MULTILINE.search(self.text)
        if is_multi_quote_header:
            self.text = MULTI_QUOTE_HDR_REGEX.sub(
                lambda _: is_multi_quote_header.groups()[0].replace("\n", ""),
                self.text,
            )

        # Fix Outlook-style replies where the reply sits immediately above a
        # signature boundary line.
        self.text = re.sub(r"([^\n])(?=\n ?[_-]{7,})", "\\1\n", self.text, flags=re.MULTILINE)

        self.lines = self.text.split("\n")
        self.lines.reverse()

        for line in self.lines:
            self._scan_line(line)

        self._finish_fragment()
        self.fragments.reverse()
        return self

    @property
    def reply(self) -> str:
        return "\n".join(f.content for f in self.fragments if not (f.hidden or f.quoted))

    def _scan_line(self, line: str) -> None:
        is_quote_header = QUOTE_HDR_REGEX.match(line) is not None
        is_quoted = QUOTED_REGEX.match(line) is not None
        is_header = is_quote_header or HEADER_REGEX.match(line) is not None

        if self.fragment and len(line.strip()) == 0:
            if SIG_REGEX.match(self.fragment.lines[-1].strip()):
                self.fragment.signature = True
                self._finish_fragment()

        if self.fragment and (
            (self.fragment.headers == is_header and self.fragment.quoted == is_quoted)
            or (self.fragment.quoted and (is_quote_header or len(line.strip()) == 0))
        ):
            self.fragment.lines.append(line)
        else:
            self._finish_fragment()
            self.fragment = Fragment(is_quoted, line, headers=is_header)

    def _finish_fragment(self) -> None:
        if self.fragment:
            self.fragment.finish()
            if self.fragment.headers:
                self.found_visible = False
                for f in self.fragments:
                    f.hidden = True
            if not self.found_visible:
                if (
                    self.fragment.quoted
                    or self.fragment.headers
                    or self.fragment.signature
                    or len(self.fragment.content.strip()) == 0
                ):
                    self.fragment.hidden = True
                else:
                    self.found_visible = True
            self.fragments.append(self.fragment)
        self.fragment = None


def strip_email_reply_quotes(text: str) -> str:
    message = EmailMessage(text).read()
    visible_parts = [fragment.content for fragment in message.fragments if not fragment.hidden]
    return "\n".join(visible_parts).strip()
