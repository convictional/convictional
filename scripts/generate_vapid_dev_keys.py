#!/usr/bin/env python3
"""Generate a local VAPID keypair for dev push notifications.

Writes VAPID_PUBLIC_KEY (base64url) and VAPID_PRIVATE_KEY (PEM, with newlines
escaped to fit on one line) into .env.secrets. Refuses to overwrite an
existing pair without --force.
"""

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from py_vapid.utils import b64urlencode

from scripts.helpers import green_text, red_text, yellow_text

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.secrets"


def application_server_key(vapid: Vapid) -> str:
    """The base64url form of the public key the browser passes to subscribe()."""
    raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return b64urlencode(raw)


def private_key_envline(vapid: Vapid) -> str:
    # pywebpush calls Vapid.from_string on this value, which expects the inner
    # PKCS#8 DER bytes base64url-encoded — *not* the full PEM. A PEM here
    # tripped from_string's "strip newlines then base64-decode" path on the
    # ----- markers and failed with an ASN.1 length error at send time.
    der = vapid.private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return f"VAPID_PRIVATE_KEY={b64urlencode(der)}"


def has_existing_vapid(text: str) -> bool:
    return any(
        line.startswith("VAPID_PUBLIC_KEY=") or line.startswith("VAPID_PRIVATE_KEY=") for line in text.splitlines()
    )


def strip_existing_vapid(text: str) -> str:
    keep = [
        line
        for line in text.splitlines()
        if not (line.startswith("VAPID_PUBLIC_KEY=") or line.startswith("VAPID_PRIVATE_KEY="))
    ]
    return "\n".join(keep).rstrip() + "\n"


def main(force: bool) -> int:
    if not ENV_FILE.exists():
        print(red_text(f".env.secrets not found at {ENV_FILE}"))
        print("Create it first (see docs/development.md → Configuration), then re-run.")
        return 1

    current = ENV_FILE.read_text()
    if has_existing_vapid(current) and not force:
        print(yellow_text("VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY already present in .env.secrets."))
        print("Re-run with --force to replace them, or remove the lines manually.")
        return 1

    vapid = Vapid()
    vapid.generate_keys()

    public_key = application_server_key(vapid)
    public_line = f"VAPID_PUBLIC_KEY={public_key}"
    private_line = private_key_envline(vapid)

    new_body = strip_existing_vapid(current).rstrip() + f"\n\n{public_line}\n{private_line}\n"
    ENV_FILE.write_text(new_body)

    print(green_text("✓ VAPID dev keypair written to .env.secrets"))
    print(f"  public key prefix: {public_key[:12]}…")
    print("  Restart `make server` to pick up the new env vars.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing VAPID pair in .env.secrets")
    args = parser.parse_args()
    sys.exit(main(force=args.force))
