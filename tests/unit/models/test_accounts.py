import io

import pytest
from PIL import Image

from app.models.accounts import OrganizationUpdatesConfiguration, User, process_avatar_image
from config.enums import UpdateFrequency
from config.settings import settings
from infra.oauth import Token
from lib.images import ImageProcessingError
from tests.helpers.images import png_bytes


def test_is_login_blocked():
    with settings.override():
        settings.blocked_emails = {"kris.braun@gmail.com"}
        settings.blocked_oauth_subs = {"101356682725729218008"}

        # Blocked by email, including Gmail dot/+tag aliases and case — an exact-string
        # block would be trivially bypassable.
        for email in [
            "kris.braun@gmail.com",
            "k.r.i.s.braun@gmail.com",
            "krisbraun+anything@gmail.com",
            "KrisBraun@gmail.com",
        ]:
            assert User.is_login_blocked(Token.fake(email).id_token_model) is True

        # Blocked by Google subject id even when the email is changed.
        id_token = Token.fake("someone-new@example.com").id_token_model
        assert User.is_login_blocked(id_token) is False
        id_token.sub = "101356682725729218008"
        assert User.is_login_blocked(id_token) is True

        # An unrelated identity is allowed through.
        assert User.is_login_blocked(Token.fake("normal.user@example.com").id_token_model) is False

    # With an empty blocklist (the default outside production) nothing is blocked.
    assert User.is_login_blocked(Token.fake("kris.braun@gmail.com").id_token_model) is False


def test_process_avatar_image():
    # A valid upload is re-encoded to a square WebP at the policy size.
    output = process_avatar_image(png_bytes(800, 600), "image/png")
    image = Image.open(io.BytesIO(output))
    assert image.format == "WEBP"
    assert image.size == (512, 512)

    # Disallowed content type, and bytes that aren't a real image, are both rejected.
    with pytest.raises(ImageProcessingError):
        process_avatar_image(png_bytes(10, 10), "image/gif")
    with pytest.raises(ImageProcessingError):
        process_avatar_image(b"not really png bytes", "image/png")

    # Over the size cap is rejected before decoding.
    with pytest.raises(ImageProcessingError):
        process_avatar_image(b"x" * (5 * 1024 * 1024 + 1), "image/png")


def test_updates_configuration_schedule_building():
    # set_schedule builds the cron string the scheduler runs on; the hour/day_of_week
    # properties read it back.
    config = OrganizationUpdatesConfiguration()

    config.set_schedule(UpdateFrequency.WEEKLY, 9, "1")
    assert config.update_schedule == "0 9 * * 1"
    assert config.frequency == UpdateFrequency.WEEKLY
    assert config.hour == 9
    assert config.day_of_week == "1"

    # Monthly fires on the last day of the month and has no day_of_week.
    config.set_schedule(UpdateFrequency.MONTHLY, 10)
    assert config.update_schedule == "0 10 L * *"
    assert config.frequency == UpdateFrequency.MONTHLY
    assert config.hour == 10
    assert config.day_of_week is None

    # Every weekday and a representative spread of hours round-trip cleanly.
    for day in ["0", "1", "2", "3", "4", "5", "6"]:
        config.set_schedule(UpdateFrequency.WEEKLY, 0, day)
        assert config.update_schedule == f"0 0 * * {day}"
        assert config.day_of_week == day
    for hour in [0, 12, 23]:
        config.set_schedule(UpdateFrequency.WEEKLY, hour, "1")
        assert config.hour == hour


def test_updates_configuration_validate_schedule():
    config = OrganizationUpdatesConfiguration()

    # Valid weekly and monthly schedules return no error.
    assert config.validate_schedule(UpdateFrequency.WEEKLY, 9, "1") is None
    assert config.validate_schedule(UpdateFrequency.MONTHLY, 10) is None

    # Weekly requires a valid day_of_week; the hour must be 0-23.
    assert config.validate_schedule(UpdateFrequency.WEEKLY, 9, None) is not None
    assert config.validate_schedule(UpdateFrequency.WEEKLY, 9, "8") is not None
    assert config.validate_schedule(UpdateFrequency.WEEKLY, 25, "1") is not None
