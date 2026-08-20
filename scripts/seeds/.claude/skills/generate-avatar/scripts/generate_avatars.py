#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT", ""))
    if not project:
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            project = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if not project:
        print("Error: Set GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT for Vertex AI auth")
        sys.exit(1)
    # Use global endpoint instead of regional to get better availability
    return genai.Client(vertexai=True, project=project, location="global")


def _generate_image(client: genai.Client, prompt: str) -> bytes | None:
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-3-pro-image-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
                ),
            )
            if response.parts:
                for part in response.parts:
                    if part.inline_data is not None:
                        return part.inline_data.data
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_RETRY_DELAY * (2**attempt)
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s after: {e}")
                time.sleep(delay)
                continue
            print(f"  Failed after {MAX_RETRIES} attempts: {e}")
            return None

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_RETRY_DELAY * (2**attempt)
            print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s (no image in response)")
            time.sleep(delay)

    return None


def _resize_to_256(image_data: bytes) -> bytes:
    img = Image.open(BytesIO(image_data))
    img = img.resize((256, 256), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Generate a single avatar image")
    parser.add_argument("output", help="Output PNG file path")
    parser.add_argument(
        "--description",
        required=True,
        help="What to generate (e.g. 'Nadia, a CEO')",
    )
    parser.add_argument(
        "--style",
        default=(
            "LinkedIn profile picture style headshot, extreme close-up composition, "
            "tight crop from top of head to just below collarbone, face fills approximately "
            "60 percent of the frame height, only the head and a sliver of shoulders visible, "
            "soft natural lighting, blurred office background"
        ),
        help="Art style for the portrait",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = f"{args.style}. {args.description}. No text overlays."

    print(f"  Style: {args.style}")
    print(f"  Generating {output_path.stem}...")

    client = _get_client()
    image_data = _generate_image(client, prompt)
    if image_data is None:
        print("  Error: No image generated")
        sys.exit(1)

    resized = _resize_to_256(image_data)
    output_path.write_bytes(resized)
    print(f"  Saved {output_path} ({len(resized) // 1024}KB)")


if __name__ == "__main__":
    main()
