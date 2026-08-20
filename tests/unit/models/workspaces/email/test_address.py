from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailMessage


def test_email_address_parsing():
    # Test parsing with display name format using parse method
    addr = EmailAddress.parse("John Doe <john@example.com>")
    assert addr.email == "john@example.com"
    assert addr.name == "John Doe"
    assert addr.display_name == "John Doe <john@example.com>"
    assert addr.has_display_name is True

    # Email without display name - uses parse method
    addr = EmailAddress.parse("jane@example.com")
    assert addr.email == "jane@example.com"
    assert addr.name == "jane"
    assert addr.display_name == "jane <jane@example.com>"
    assert addr.has_display_name is False

    # Email with quoted display name
    addr = EmailAddress.parse('"Jane Smith" <jane.smith@example.com>')
    assert addr.email == "jane.smith@example.com"
    assert addr.name == "Jane Smith"
    assert addr.display_name == "Jane Smith <jane.smith@example.com>"
    assert addr.has_display_name is True

    # Email with complex username
    addr = EmailAddress.parse("user.name+tag@example.org")
    assert addr.email == "user.name+tag@example.org"
    assert addr.name == "user.name+tag"
    assert addr.display_name == "user.name+tag <user.name+tag@example.org>"
    assert addr.has_display_name is False

    # Email with angle brackets but no display name
    addr = EmailAddress.parse("<dana.holbrook@example.com>")
    assert addr.email == "dana.holbrook@example.com"
    assert addr.name == "dana.holbrook"
    assert addr.display_name == "dana.holbrook <dana.holbrook@example.com>"
    assert addr.has_display_name is False

    # Email with display name containing special characters (quoted)
    addr = EmailAddress.parse('"Dr. John O\'Connor" <j.oconnor@hospital.com>')
    assert addr.email == "j.oconnor@hospital.com"
    assert addr.name == "Dr. John O'Connor"
    assert addr.display_name == "Dr. John O'Connor <j.oconnor@hospital.com>"
    assert addr.has_display_name is True

    # Direct constructor with name and email parameters
    addr = EmailAddress("John Doe", "user@example.com")
    assert addr.email == "user@example.com"
    assert addr.name == "John Doe"
    assert addr.display_name == "John Doe <user@example.com>"
    assert addr.has_display_name is True

    # Direct constructor with different name
    addr = EmailAddress("Jane Smith", "jane@example.com")
    assert addr.email == "jane@example.com"
    assert addr.name == "Jane Smith"
    assert addr.display_name == "Jane Smith <jane@example.com>"
    assert addr.has_display_name is True

    # Direct constructor with username-like name
    addr = EmailAddress("user2", "user2@example.com")
    assert addr.email == "user2@example.com"
    assert addr.name == "user2"
    assert addr.display_name == "user2 <user2@example.com>"
    assert addr.has_display_name is False

    # First name property
    addr = EmailAddress("John Doe", "john@example.com")
    assert addr.first_name == "John"

    addr = EmailAddress("jane", "jane@example.com")
    assert addr.first_name == "jane"

    addr = EmailAddress("Dr. John O'Connor", "j.oconnor@hospital.com")
    assert addr.first_name == "Dr."

    # Email with comma in the display name (quoted)
    addr = EmailAddress.parse('"Doe, John" <john.doe@example.com>')
    assert addr.email == "john.doe@example.com"
    assert addr.name == "Doe, John"
    assert addr.display_name == "Doe, John <john.doe@example.com>"
    assert addr.has_display_name is True


def test_email_address_build():
    # Test building with email and name
    addr = EmailAddress.build("marcus.larkin@example.com", "Marcus Larkin")
    assert addr.email == "marcus.larkin@example.com"
    assert addr.name == "Marcus Larkin"
    assert addr.display_name == "Marcus Larkin <marcus.larkin@example.com>"
    assert addr.has_display_name is True

    # Test building with email only (empty name)
    addr = EmailAddress.build("marcus.larkin@example.com", "")
    assert addr.email == "marcus.larkin@example.com"
    assert addr.name == "marcus.larkin"
    assert addr.display_name == "marcus.larkin <marcus.larkin@example.com>"
    assert addr.has_display_name is False

    # Test building with already formatted email string
    addr = EmailAddress.build("John Doe <john@example.com>", "Different Name")
    assert addr.email == "john@example.com"
    # The provided name should be used to create a new display name format
    assert addr.name == "Different Name"
    assert addr.display_name == "Different Name <john@example.com>"

    # Test building with a user name that should fail validation
    addr = EmailAddress.build("john@example.com", "john@example.com")
    assert addr.email == "john@example.com"
    # We should fallback to using original parsed email address
    assert addr.name == "john"
    assert addr.display_name == "john <john@example.com>"


def test_email_address_parse_list_addresses():
    # Test comma-separated email addresses
    addresses = EmailAddress.parse_list_addresses("john@example.com, Jane Smith <jane@example.com>")
    assert addresses == ["john@example.com", "jane@example.com"]

    # Test single email
    addresses = EmailAddress.parse_list_addresses("user@example.com")
    assert addresses == ["user@example.com"]

    # Test empty/None input
    addresses = EmailAddress.parse_list_addresses(None)
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses("")
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses("   ")
    assert addresses == []

    # Test with extra whitespace
    addresses = EmailAddress.parse_list_addresses("  john@example.com  ,  jane@example.com  ")
    assert addresses == ["john@example.com", "jane@example.com"]

    # Test with commas in the display name (quoted)
    addresses = EmailAddress.parse_list_addresses('"Doe, John" <john.doe@example.com>')
    assert addresses == ["john.doe@example.com"]

    # Test with commas in the display name (unquoted)
    addresses = EmailAddress.parse_list_addresses("Doe, John <john.doe@example.com>")
    assert addresses == ["john.doe@example.com"]

    addresses = EmailAddress.parse_list_addresses(
        "Doe, John <john.doe@example.com>, Smith, Jane <smith.jane@example.com>"
    )
    assert addresses == ["john.doe@example.com", "smith.jane@example.com"]

    # Test malformed email with excessive whitespace in display name
    malformed_display_name = "user@omg.no.prod.outlook.com"
    excessive_whitespace = " " * 1000
    embedded_header = "Date:Tue, 02 Dec 2025 16:55:52 -0500"
    malformed_email = f'"{malformed_display_name}{excessive_whitespace}{embedded_header}" <user@yprod.outlook.com>'
    addresses = EmailAddress.parse_list_addresses(malformed_email)
    assert addresses == ["user@yprod.outlook.com"]


def test_email_address_placeholder_filtering():
    # Test filtering "Undisclosed recipients:;"
    addresses = EmailAddress.parse_list_addresses("Undisclosed recipients:;")
    assert addresses == []

    # Test filtering "Undisclosed recipients" without semicolon
    addresses = EmailAddress.parse_list_addresses("Undisclosed recipients:")
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses("Undisclosed recipients")
    assert addresses == []

    # Test case-insensitive matching
    addresses = EmailAddress.parse_list_addresses("undisclosed recipients:;")
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses("UNDISCLOSED RECIPIENTS:;")
    assert addresses == []

    # Test with hyphenated variant
    addresses = EmailAddress.parse_list_addresses("undisclosed-recipients:;")
    assert addresses == []

    # Test mixed list with valid and placeholder addresses
    # In practice, "Undisclosed recipients" appears alone or at the end of a list
    addresses = EmailAddress.parse_list_addresses("john@example.com, jane@example.com, Undisclosed recipients:;")
    assert addresses == ["john@example.com", "jane@example.com"]

    addresses = EmailAddress.parse_list_addresses("Undisclosed recipients:;, john@example.com, jane@example.com")
    assert addresses == ["john@example.com", "jane@example.com"]

    # Test with display name format
    addresses = EmailAddress.parse_list_addresses(
        "John Doe <john@example.com>, Jane Smith <jane@example.com>, Undisclosed recipients:"
    )
    assert addresses == ["john@example.com", "jane@example.com"]

    # Test when only placeholders are present
    addresses = EmailAddress.parse_list_addresses("Undisclosed recipients:;, undisclosed-recipients")
    assert addresses == []


def test_email_address_parse_list_addresses_safe():
    # Normal operation - same as parse_list_addresses
    addresses = EmailAddress.parse_list_addresses_safe("john@example.com, jane@example.com")
    assert addresses == ["john@example.com", "jane@example.com"]

    # With display names
    addresses = EmailAddress.parse_list_addresses_safe("John Doe <john@example.com>")
    assert addresses == ["john@example.com"]

    # Empty input
    addresses = EmailAddress.parse_list_addresses_safe(None)
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses_safe("")
    assert addresses == []

    # Mixed valid and invalid - keeps valid ones
    addresses = EmailAddress.parse_list_addresses_safe("john@example.com, invalid, jane@example.com")
    assert addresses == ["john@example.com", "jane@example.com"]

    # All invalid - returns empty list instead of raising
    addresses = EmailAddress.parse_list_addresses_safe("invalid1, invalid2")
    assert addresses == []

    addresses = EmailAddress.parse_list_addresses_safe("not-an-email")
    assert addresses == []

    # Placeholders still work
    addresses = EmailAddress.parse_list_addresses_safe("Undisclosed recipients:;")
    assert addresses == []


def test_display_from_formatting():
    test_cases = [
        ("John Doe <john@example.com>", "John Doe <john@example.com>"),
        ("john@example.com", "john <john@example.com>"),
    ]

    for sender, expected in test_cases:
        email = EmailMessage(sender=sender, subject="Test", to=["recipient@example.com"])
        assert str(email.sender_address) == expected


def test_is_valid_email():
    # Valid emails
    assert EmailAddress.is_valid_email("user@example.com") is True
    assert EmailAddress.is_valid_email("user.name@example.com") is True
    assert EmailAddress.is_valid_email("user+tag@example.org") is True
    assert EmailAddress.is_valid_email("user@domain.co.uk") is True
    assert EmailAddress.is_valid_email("123@example.com") is True
    assert EmailAddress.is_valid_email("a" * 244 + "@example.com") is True

    # Invalid emails
    assert EmailAddress.is_valid_email("") is False
    assert EmailAddress.is_valid_email("   ") is False
    assert EmailAddress.is_valid_email("user@") is False
    assert EmailAddress.is_valid_email("@domain.com") is False
    assert EmailAddress.is_valid_email("invalid") is False
    assert EmailAddress.is_valid_email("user@domain") is False
    assert EmailAddress.is_valid_email("user@@domain.com") is False
    assert EmailAddress.is_valid_email("user@domain.") is False
    assert EmailAddress.is_valid_email("user@.domain.com") is False
    assert EmailAddress.is_valid_email("user@domain..com") is False


def test_email_address_parsing_malformed_display_name():
    # Test quoted email as display name
    parsed = EmailAddress.parse('"harriet@example.com" <harriet@example.com>')
    assert parsed.email == "harriet@example.com"
    assert parsed.name == "harriet@example.com"
    assert parsed.display_name == "harriet@example.com <harriet@example.com>"
    assert parsed.has_display_name

    # Test with non-quoted version
    parsed = EmailAddress.parse("harriet@example.com <harriet@example.com>")
    assert parsed.email == "harriet@example.com"
    assert parsed.name == "harriet@example.com"
    assert parsed.display_name == "harriet@example.com <harriet@example.com>"

    # Test safe parsing works for both formats
    safe_parsed = EmailAddress.parse_safe("harriet@example.com <harriet@example.com>")
    assert safe_parsed is not None
    assert safe_parsed.email == "harriet@example.com"

    # Test Gmail's problematic address with angle brackets in display name
    parsed = EmailAddress.parse("Indigo <> Nexera <kia@nexeradistribution.com>")
    assert parsed.email == "kia@nexeradistribution.com"
    assert parsed.name == "Indigo <> Nexera"

    # Test other malformed formats that should be handled gracefully
    test_cases = [
        '"email@domain.com" <email@domain.com>',  # Quoted email as display name
        '"user@test.com" <user@test.com>',  # Another quoted version
        '"test.user@example.org" <test.user@example.org>',  # Complex quoted version
    ]

    for test_case in test_cases:
        parsed = EmailAddress.parse(test_case)
        # Extract expected email from the angle brackets
        expected_email = test_case.split("<")[1].rstrip(">")
        assert parsed.email == expected_email
        # The display name should be the quoted part without quotes
        expected_name = test_case.split('"')[1]
        assert parsed.name == expected_name
