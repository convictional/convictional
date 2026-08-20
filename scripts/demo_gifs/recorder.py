import subprocess
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Browser, StorageState, async_playwright

from config.settings import settings
from scripts.demo_gifs.flows import Flow
from scripts.demo_gifs.scene import HEIGHT, WIDTH, Scene
from scripts.demo_gifs.server import dev_server
from scripts.helpers import green_text

CURSOR_JS = Path(__file__).parent / "cursor.js"
KEYS_JS = Path(__file__).parent / "keys.js"
OUTPUT_DIR = settings.root / "tmp" / "demo_gifs"
INSTALL_DIR = settings.root / "static" / "images"

# GIFs animate in email clients where MP4/WebP/APNG do not, so GIF is the delivery format.
FPS = 8
QUALITY = 90


def _convert_to_gif(webm: Path, out: Path, trim: float = 0.0) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_cmd = ["ffmpeg", "-v", "error"]
    if trim > 0:
        ffmpeg_cmd += ["-ss", f"{trim:.2f}"]
    ffmpeg_cmd += ["-i", str(webm), "-f", "yuv4mpegpipe", "-pix_fmt", "yuv420p", "-"]
    ffmpeg = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)
    gifski = subprocess.Popen(
        ["gifski", "-o", str(out), "--fps", str(FPS), "--width", str(WIDTH), "--quality", str(QUALITY), "-"],
        stdin=ffmpeg.stdout,
    )
    if ffmpeg.stdout:
        ffmpeg.stdout.close()
    gifski_code = gifski.wait()
    ffmpeg.wait()
    if gifski_code != 0:
        raise RuntimeError(f"gifski failed with exit code {gifski_code} for {out.name}")


@dataclass
class Recorder:
    browser: Browser
    base_url: str
    storage_state: StorageState

    @staticmethod
    async def login(browser: Browser, base_url: str, email: str) -> StorageState:
        """Log in via fake auth in a throwaway context and return its storage state.

        Recording a fresh context seeded with this state means each video opens directly
        on the flow's content — no login screen to trim out.
        """
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(base_url)
        email_input = page.locator('input[type="email"][name="email"]')
        await email_input.fill(email)
        await email_input.press("Enter")
        await page.wait_for_url("**/", wait_until="domcontentloaded")
        state = await context.storage_state()
        await context.close()
        return state

    async def record(self, flow: Flow) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        context = await self.browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(OUTPUT_DIR),
            record_video_size={"width": WIDTH, "height": HEIGHT},
            storage_state=self.storage_state,
        )
        if flow.show_cursor:
            await context.add_init_script(path=str(CURSOR_JS))
        if flow.show_keys:
            await context.add_init_script(path=str(KEYS_JS))
        page = await context.new_page()

        scene = Scene(page=page, base_url=self.base_url, show_cursor=flow.show_cursor)
        await flow.run(scene)

        video = page.video
        await context.close()  # video is flushed on context close
        webm = Path(await video.path()) if video else None
        if webm is None:
            raise RuntimeError(f"No video recorded for flow {flow.name}")

        out = OUTPUT_DIR / f"{flow.name}.gif"
        _convert_to_gif(webm, out, trim=scene.lead_in)
        webm.unlink(missing_ok=True)
        return out


async def record_flows(flows: list[Flow], email: str) -> list[Path]:
    results: list[Path] = []
    async with dev_server() as base_url, async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        state = await Recorder.login(browser, base_url, email)
        recorder = Recorder(browser=browser, base_url=base_url, storage_state=state)
        for flow in flows:
            print(f"  ▶ recording {flow.name}...")
            out = await recorder.record(flow)
            size_kb = out.stat().st_size // 1024
            print(green_text(f"    ✓ {out.relative_to(settings.root)} ({size_kb} KB)"))
            results.append(out)
        await browser.close()
    return results
