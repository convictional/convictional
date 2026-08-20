import argparse
import asyncio
import shutil

from scripts.demo_gifs.flows import FLOWS, Flow
from scripts.demo_gifs.recorder import INSTALL_DIR, record_flows

DEFAULT_EMAIL = "darren@ellery.ai"


def _resolve_flows(names: list[str] | None) -> list[Flow]:
    if not names:
        return FLOWS
    by_name = {flow.name: flow for flow in FLOWS}
    resolved = []
    for name in names:
        if name not in by_name:
            raise SystemExit(f"Unknown flow: {name}\nAvailable: {', '.join(by_name)}")
        resolved.append(by_name[name])
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Record onboarding demo GIFs from seeded demo data.")
    parser.add_argument("flows", nargs="*", help="Flow names to record (default: all)")
    parser.add_argument("--list", action="store_true", help="List available flows")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Seed user to log in as")
    parser.add_argument(
        "--install", action="store_true", help=f"Copy recorded GIFs into {INSTALL_DIR} (overwrites assets)"
    )
    args = parser.parse_args()

    if args.list:
        for flow in FLOWS:
            print(f"  - {flow.name}")
        return

    flows = _resolve_flows(args.flows or None)
    print(f"Recording {len(flows)} flow(s) as {args.email}...")
    outputs = asyncio.run(record_flows(flows, args.email))

    if args.install:
        for out in outputs:
            dest = INSTALL_DIR / out.name
            shutil.copyfile(out, dest)
            print(f"  installed → {dest.relative_to(INSTALL_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
