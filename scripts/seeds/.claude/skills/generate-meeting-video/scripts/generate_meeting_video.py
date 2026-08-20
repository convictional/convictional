#!/usr/bin/env python3

import argparse
import math
import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw

MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2
POLL_INTERVAL = 10
POLL_TIMEOUT = 300

VEO_MODEL = "veo-2.0-generate-001"

CANVAS_W, CANVAS_H = 1280, 720
BG_COLOR = (26, 26, 46)
TILE_PADDING = 12
TILE_RADIUS = 12

DEFAULT_PROMPT = (
    "A video conference call, colleagues in a virtual meeting grid, "
    "subtle natural head movements and expressions, professional webcam quality, "
    "soft lighting, slight ambient motion"
)


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
    return genai.Client(vertexai=True, project=project, location="global")


def _find_seeds_dir() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if current.name == "seeds":
            return current
        current = current.parent
    print("Error: Could not find seeds directory")
    sys.exit(1)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def _composite_grid(avatars_dir: Path) -> Image.Image:
    pngs = sorted(avatars_dir.glob("*.png"))
    if not pngs:
        print(f"Error: No avatar PNGs found in {avatars_dir}")
        sys.exit(1)

    n = len(pngs)
    cols = min(n, 3)
    rows = math.ceil(n / cols)

    tile_w = (CANVAS_W - TILE_PADDING * (cols + 1)) // cols
    tile_h = (CANVAS_H - TILE_PADDING * (rows + 1)) // rows

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)

    for i, png_path in enumerate(pngs):
        row, col = divmod(i, cols)
        row_count = min(cols, n - row * cols)
        row_width = row_count * tile_w + (row_count - 1) * TILE_PADDING
        x_offset = (CANVAS_W - row_width) // 2

        x = x_offset + col * (tile_w + TILE_PADDING)
        y = TILE_PADDING + row * (tile_h + TILE_PADDING)

        avatar = Image.open(png_path).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
        mask = _rounded_mask((tile_w, tile_h), TILE_RADIUS)
        canvas.paste(avatar, (x, y), mask)

    return canvas


def _reimagine_grid(client: genai.Client, image: Image.Image) -> Image.Image:
    prompt = (
        "Transform this video call grid into a photorealistic screenshot of a web meeting. "
        "Keep the exact same people with the same faces, hair, and skin tones. "
        "Each person should be sitting at a desk in a casual home office setting, "
        "wearing casual clothing, framed from the chest up as seen on a webcam. "
        "Maintain the grid layout. Soft natural lighting from a window. "
        "No text overlays, no UI elements, no watermarks."
    )

    buf = BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-3-pro-image-preview",
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(aspect_ratio="16:9", image_size="1K"),
                ),
            )
            if response.parts:
                for part in response.parts:
                    if part.inline_data is not None:
                        result = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                        return result.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_RETRY_DELAY * (2**attempt)
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s after: {e}")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Reimagine failed after {MAX_RETRIES} attempts: {e}") from e

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_RETRY_DELAY * (2**attempt)
            print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s (no image in response)")
            time.sleep(delay)

    raise RuntimeError("Reimagine failed: no image returned after all retries")


def _animate_image(client: genai.Client, image: Image.Image, prompt: str) -> bytes | None:
    buf = BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    for attempt in range(MAX_RETRIES):
        try:
            operation = client.models.generate_videos(
                model=VEO_MODEL,
                prompt=prompt,
                image=types.Image(image_bytes=image_bytes, mime_type="image/png"),
                config=types.GenerateVideosConfig(
                    aspect_ratio="16:9",
                    number_of_videos=1,
                ),
            )

            start = time.time()
            while not operation.done:
                if time.time() - start > POLL_TIMEOUT:
                    print(f"  Timeout after {POLL_TIMEOUT}s waiting for video generation")
                    return None
                time.sleep(POLL_INTERVAL)
                operation = client.operations.get(operation)

            if operation.response and operation.response.generated_videos:
                video = operation.response.generated_videos[0]
                return client.files.download(file=video.video)

            print("  No video in response")

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_RETRY_DELAY * (2**attempt)
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s after: {e}")
                time.sleep(delay)
                continue
            print(f"  Failed after {MAX_RETRIES} attempts: {e}")
            return None

    return None


def main():
    parser = argparse.ArgumentParser(description="Generate a meeting recording video from scenario avatars")
    parser.add_argument("output", help="Output MP4 file path")
    parser.add_argument("--scenario", required=True, help="Scenario name (to find avatars directory)")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Custom animation prompt")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seeds_dir = _find_seeds_dir()
    avatars_dir = seeds_dir / args.scenario / "avatars"
    if not avatars_dir.is_dir():
        print(f"Error: Avatars directory not found: {avatars_dir}")
        sys.exit(1)

    print(f"  Compositing avatars from {avatars_dir}...")
    composite = _composite_grid(avatars_dir)

    composite_path = output_path.with_suffix(".composite.png")
    composite.save(composite_path, format="PNG")
    print(f"  Saved composite: {composite_path}")

    client = _get_client()

    print("  Reimagining grid with Gemini...")
    reimagined = _reimagine_grid(client, composite)
    reimagined_path = output_path.with_suffix(".reimagined.png")
    reimagined.save(reimagined_path, format="PNG")
    print(f"  Saved reimagined: {reimagined_path}")

    print("  Animating with Veo...")
    video_data = _animate_image(client, reimagined, args.prompt)
    if video_data is None:
        print("  Error: No video generated")
        sys.exit(1)

    output_path.write_bytes(video_data)
    print(f"  Saved {output_path} ({len(video_data) // 1024}KB)")

    composite_path.unlink(missing_ok=True)
    reimagined_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
