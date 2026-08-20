"""Reset the Gmail integration across every user.

This used to be a background job (`ResetGmailIntegrationJob`) but was moved to a
script because running it in production would TRUNCATE the email tables and
force every user to re-auth with Gmail. The intent is local-dev use only — for
example, stopping the Gmail watch at end of day to avoid a flood of replayed
emails on next startup.
"""

import argparse
import asyncio

from app.models.accounts import User
from app.models.collaboration.content import Content
from config.enums import AuthenticationProvider, ContentType, Integration
from infra.db import transaction
from integrations.google.gmail import get_google_api_client
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from scripts.helpers import green_text, in_app_lifespan, red_text, yellow_text


async def reset():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually perform the reset. Without this flag the script only prints what it would do.",
    )
    args = parser.parse_args()

    print(
        yellow_text(
            "About to TRUNCATE: emailthread, emailcontact, gmailaccount, mailboxentry; stop every Gmail watch; "
            "and remove the Gmail integration from every user. THIS IS IRREVERSIBLE."
        )
    )

    if not args.yes:
        print(red_text("Aborting: pass --yes to actually run."))
        return

    gmail_accounts = await GmailAccount.all().prefetch_related("user__oauth_tokens")
    for gmail_account in gmail_accounts:
        google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if google_token and gmail_account.user.is_integrated_with(Integration.GMAIL):
            google = await get_google_api_client(gmail_account.user, gmail_account)
            await google.stop_watch()
            await google_token.remove_scopes(GOOGLE_GMAIL_SCOPES)
            await gmail_account.user.remove_integration(Integration.GMAIL)

    async with transaction() as connection:
        users_with_google_tokens = (
            await User.filter(User.filters.by_auth_provider(AuthenticationProvider.GOOGLE))
            .using_db(connection)
            .prefetch_related("oauth_tokens")
        )
        for user in users_with_google_tokens:
            google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
            if google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
                await google_token.remove_scopes(GOOGLE_GMAIL_SCOPES, using_db=connection)
                await user.remove_integration(Integration.GMAIL, using_db=connection)

        # CASCADE on emailthread handles emailmessage and emailattachment.
        await connection.execute_script('TRUNCATE TABLE "emailthread" CASCADE')
        await connection.execute_script('TRUNCATE TABLE "emailcontact" CASCADE')
        await connection.execute_script('TRUNCATE TABLE "gmailaccount" CASCADE')
        await connection.execute_script('TRUNCATE TABLE "mailboxentry" CASCADE')
        await Content.filter(Content.filters.by_content_type(ContentType.EMAIL_THREAD)).using_db(connection).delete()

    print(green_text("Gmail integration reset complete."))


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(reset()))
