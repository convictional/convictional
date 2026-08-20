import asyncio
import sys

from app.models.accounts import User
from infra.db import transaction
from integrations.google.models import GmailAccount
from scripts.helpers import green_text, in_database_context, red_text


async def reset():
    email = sys.argv[1] if len(sys.argv) > 1 else None
    if not email:
        print(red_text("Usage: make script ARGS='scripts/reset_user_onboarding.py user@example.com'"))
        return

    user = await User.get_or_none(email=email)

    if not user:
        print(red_text(f"User {email} not found"))
        return

    async with transaction() as conn:
        user.integrations = []
        user.onboarding_mailbox_sync_started_at = None
        user.onboarding_mailbox_sync_completed_at = None
        await user.save(
            update_fields=[
                "integrations",
                "onboarding_mailbox_sync_started_at",
                "onboarding_mailbox_sync_completed_at",
            ],
            using_db=conn,
        )

        deleted = await GmailAccount.filter(user_id=user.id).using_db(conn).delete()

    print(green_text(f"Reset {email}: cleared integrations, onboarding state, deleted {deleted} GmailAccount(s)"))


asyncio.run(in_database_context(reset()))
