import re
from dataclasses import dataclass
from typing import Self

# EMAIL_VALIDATION_PATTERN is from https://www.regular-expressions.info/email.html
EMAIL_VALIDATION_PATTERN = re.compile(
    r"\A[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z",
    re.IGNORECASE,
)
EMAIL_DISPLAY_NAME_PATTERN = r'^(?:"([^"]+)"|(.+?))\s*<([^>]+)>\s*$'
BCC_EMAIL_ADDRESS_PLACEHOLDERS = ["undisclosed recipients", "undisclosed-recipients"]


@dataclass
class EmailAddress:
    name: str
    email: str

    @classmethod
    def parse(cls, value: str | Self) -> "EmailAddress":
        """Parse email address from string or return existing EmailAddress instance."""
        if isinstance(value, cls):
            return value

        if not value or not isinstance(value, str):
            raise ValueError("Email address must be a string")

        # Remove extra whitespace
        value = value.strip()
        value = " ".join(value.split())
        if not value:
            raise ValueError("Email address must be a non-empty string")

        # Check for display name format: "Name <email@example.com>" or Name <email@example.com>
        match = re.match(EMAIL_DISPLAY_NAME_PATTERN, value)
        if match:
            quoted_name, unquoted_name, email = match.groups()
            name = (quoted_name or unquoted_name).strip()
            email = email.strip()
            if not EMAIL_VALIDATION_PATTERN.match(email):
                raise ValueError(f"Invalid email address: {email}")
            return cls(name=name if name else email.split("@")[0], email=email)

        # Check for angle bracket format without display name: <email@example.com>
        if value.startswith("<") and value.endswith(">"):
            email = value[1:-1].strip()
            if not EMAIL_VALIDATION_PATTERN.match(email):
                raise ValueError(f"Invalid email address: {email}")
            return cls(name=email.split("@")[0], email=email)

        # Simple email format
        if not EMAIL_VALIDATION_PATTERN.match(value):
            raise ValueError(f"Invalid email address: {value}")
        username = value.split("@")[0]
        return cls(name=username.strip(), email=value.strip())

    @classmethod
    def parse_safe(cls, value: str | Self) -> "EmailAddress | None":
        """Parse email address from string, return None if invalid."""
        try:
            return cls.parse(value)
        except ValueError:
            return None

    @classmethod
    def build(cls, email_string: str, name: str | None = None) -> "EmailAddress":
        """Build EmailAddress from email string and optional name."""
        parsed = cls.parse(email_string)
        if name and name.strip():
            # If the provided name is actually an email address, fallback to username
            if cls.is_valid_email(name.strip()):
                return parsed
            try:
                return cls.parse(f"{name} <{parsed.email}>")
            except ValueError:
                pass
        return parsed

    @classmethod
    def is_valid_email(cls, email: str) -> bool:
        """Check if an email address string is valid."""
        if not email or not isinstance(email, str):
            return False
        try:
            cls.parse(email)
            return True
        except ValueError:
            return False

    @staticmethod
    def _split_email_list(email_string: str) -> list[str]:
        """Split comma-separated email list handling unquoted display names with commas.

        This mirrors the JavaScript implementation in emailAddress.ts.
        """
        parts: list[str] = []
        current = ""
        inside_quotes = False
        inside_angle_brackets = False

        for i, char in enumerate(email_string):
            prev_char = email_string[i - 1] if i > 0 else ""

            if char == '"' and prev_char != "\\":
                inside_quotes = not inside_quotes
                current += char
            elif char == "<" and not inside_quotes:
                inside_angle_brackets = True
                current += char
            elif char == ">" and not inside_quotes:
                inside_angle_brackets = False
                current += char
            elif char == "," and not inside_quotes and not inside_angle_brackets:
                # Look ahead to detect if comma is part of unquoted display name
                remaining = email_string[i + 1 :]
                next_angle = remaining.find("<")
                next_comma = remaining.find(",")
                has_content = len(current.strip()) > 0

                # If there's a < coming up and we don't have an email yet,
                # this comma is part of the display name
                if has_content and next_angle != -1 and (next_comma == -1 or next_angle < next_comma):
                    has_email = "@" in current or ">" in current
                    if not has_email:
                        current += char  # Keep comma as part of display name
                        continue

                # Otherwise, comma is a separator
                parts.append(current.strip())
                current = ""
            else:
                current += char

        parts.append(current.strip())
        return parts

    @classmethod
    def parse_list(cls, comma_separated_email_string: str | None) -> list["EmailAddress"]:
        """Parse comma-separated email addresses that may include display names."""
        if not comma_separated_email_string or not comma_separated_email_string.strip():
            return []

        addresses = []
        filtered_placeholders = 0
        # Use custom split logic to handle unquoted display names with commas
        parts = cls._split_email_list(comma_separated_email_string)

        for part in parts:
            if not part:
                continue

            # Filter out email placeholder values (case-insensitive)
            part_lower = part.strip().lower()

            if any(placeholder in part_lower for placeholder in BCC_EMAIL_ADDRESS_PLACEHOLDERS):
                filtered_placeholders += 1
                continue

            parsed = cls.parse_safe(part)
            if parsed:
                addresses.append(parsed)

        # If we got no valid addresses but had input (and didn't filter out any placeholders), raise an error
        if not addresses and parts and filtered_placeholders == 0:
            raise ValueError("Invalid email address format")

        return addresses

    @classmethod
    def parse_list_addresses(cls, comma_separated_email_string: str | None) -> list[str]:
        """Parse comma-separated email addresses that may include display names into a list of email addresses only."""
        return [addr.email for addr in cls.parse_list(comma_separated_email_string)]

    @classmethod
    def parse_list_addresses_safe(cls, comma_separated_email_string: str | None) -> list[str]:
        """Parse comma-separated email addresses, returning empty list if all are invalid."""
        try:
            return cls.parse_list_addresses(comma_separated_email_string)
        except ValueError:
            return []

    @property
    def display_name(self) -> str:
        """Format as a display name string, i.e. 'Name <name@example.com>'."""
        return str(self)

    @property
    def has_display_name(self) -> bool:
        """Check if the name is different from the username part of email."""
        username = self.email.split("@")[0]
        return self.name != username

    @property
    def first_name(self) -> str:
        return self.name.split(" ", 1)[0] if " " in self.name else self.name

    def __str__(self) -> str:
        """Format as display string."""
        return f"{self.name} <{self.email}>"
