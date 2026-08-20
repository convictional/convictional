#!/usr/bin/env python3
import argparse
import asyncio
import time

from app.jobs.push import build_payload
from app.models.accounts import PushSubscription, User
from infra.push import send_push
from scripts.helpers import green_text, in_database_context, red_text, yellow_text


async def main(user_email: str, title: str, body: str, url_path: str) -> None:
    user = await User.filter(User.filters.by_email_exact(user_email)).first()
    if not user:
        print(red_text(f"No user found with email {user_email}"))
        return

    subscription = await PushSubscription.filter(user_id=user.id).order_by("-created_at").first()
    if not subscription:
        print(yellow_text(f"User {user.email} has no active push subscriptions."))
        return

    # Unique tag per invocation so each test fires a fresh banner. With a
    # constant tag, macOS replaces the existing Notification Center entry
    # without re-showing the banner if you didn't dismiss the previous one.
    payload = build_payload(title=title, body=body, url_path=url_path, tag=f"manual-test-{int(time.time())}")
    print(f"Sending push to {subscription.platform or 'unknown device'} ({subscription.endpoint[-12:]})…")

    result = await send_push(
        endpoint=subscription.endpoint,
        protocol=subscription.protocol,
        p256dh_key=subscription.p256dh_key,
        auth_key=subscription.auth_key,
        payload=payload,
    )

    if result.success:
        print(green_text("✓ Push accepted by relay"))
        return
    if result.subscription_invalidated:
        # Mirror what the production push job does on a 404/410: soft-delete
        # so the next dispatch skips this dead subscription.
        await subscription.soft_delete()
        print(red_text("✗ Subscription is gone (relay returned 404/410). Soft-deleted the row."))
        return
    print(red_text("✗ Push failed (retryable). Check logs."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a test push notification to a user's first active device.")
    parser.add_argument("--user-email", required=True, help="Email of the recipient user")
    parser.add_argument("--title", default="Test push", help="Notification title")
    parser.add_argument("--body", default="If you see this, push is working.", help="Notification body")
    parser.add_argument("--url-path", default="/inbox", help="Path to open when the notification is clicked")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(
        in_database_context(
            main(
                user_email=args.user_email,
                title=args.title,
                body=args.body,
                url_path=args.url_path,
            )
        )
    )
