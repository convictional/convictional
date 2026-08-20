#!/usr/bin/env python3

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

URL_RE = re.compile(r"https?://[^\s<>\"')]+")
TRAILING_PUNCT = ".,;:!?)]>"
TIMEOUT = 8.0
MAX_WORKERS = 8


def _extract_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    urls = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCT)
        urls.append(url)
    return urls


def _probe(url: str) -> tuple[str, int | None, str | None, str | None]:
    try:
        with httpx.Client(follow_redirects=True, timeout=TIMEOUT) as client:
            resp = client.head(url)
            if resp.status_code == 405:
                resp = client.get(url)
        return url, resp.status_code, str(resp.url), None
    except httpx.HTTPError as e:
        return url, None, None, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate URLs in a scenario's post bodies")
    parser.add_argument("scenario", help="Scenario directory name under scripts/seeds/")
    args = parser.parse_args()

    posts_dir = Path(__file__).parent.parent.parent.parent.parent / args.scenario / "content" / "posts"
    if not posts_dir.exists():
        print(f"Error: {posts_dir} does not exist", file=sys.stderr)
        return 2

    urls_by_file: dict[Path, list[str]] = {}
    for md_path in sorted(posts_dir.rglob("*.md")):
        urls = _extract_urls(md_path)
        if urls:
            urls_by_file[md_path] = urls

    all_urls = [(path, url) for path, urls in urls_by_file.items() for url in urls]
    if not all_urls:
        print("No URLs found in post bodies. Nothing to validate.")
        return 0

    print(f"Validating {len(all_urls)} URL(s) across {len(urls_by_file)} file(s)...\n")

    results: dict[str, tuple[int | None, str | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_probe, url): url for _, url in all_urls}
        for fut in as_completed(futures):
            url, status, final_url, error = fut.result()
            results[url] = (status, final_url, error)

    failures = 0
    for path, urls in urls_by_file.items():
        rel = path.relative_to(posts_dir.parent.parent.parent)
        for url in urls:
            status, final_url, error = results[url]
            ok = status is not None and 200 <= status < 300
            marker = "✓" if ok else "✗"
            detail = f"{status}" if status else f"ERROR ({error})"
            suffix = f" -> {final_url}" if final_url and final_url != url else ""
            print(f"  {marker} [{detail}] {url}{suffix}")
            if not ok:
                failures += 1
                print(f"      in {rel}")

    print()
    if failures:
        print(f"{failures} URL(s) failed validation. Fix or remove them before seeding.")
        return 1

    print("All URLs returned 2xx.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
