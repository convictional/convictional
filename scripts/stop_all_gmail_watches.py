"""Stop every active Gmail push-notification watch.

Moved from `StopAllGmailWatchesJob` because this is a maintenance operation
that should not be runnable from the /background_jobs UI.
"""

import argparse
import asyncio

from config.enums import AuthenticationProvider
from integrations.google.gmail import get_google_api_client
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from scripts.helpers import green_text, in_app_lifespan, red_text, yellow_text


async def stop():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually stop the watches. Without this flag the script only prints what it would do.",
    )
    args = parser.parse_args()

    print(yellow_text("About to stop every Gmail watch across every user. They will stop receiving Gmail webhooks."))
    if not args.yes:
        print(red_text("Aborting: pass --yes to actually run."))
        return

    gmail_accounts = await GmailAccount.all().prefetch_related("user__oauth_tokens")
    stopped = 0
    for gmail_account in gmail_accounts:
        google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
            google = await get_google_api_client(gmail_account.user, gmail_account)
            await google.stop_watch()
            stopped += 1

    print(green_text(f"Stopped {stopped} Gmail watch(es)."))


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(stop()))
