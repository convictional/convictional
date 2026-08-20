---
description: Generate a meeting recording video from scenario avatars using Pillow compositing and Google Veo animation
---

# Generate Meeting Video

Generate a short video recording for a demo seed meeting by compositing avatar images into a video-call grid and animating with Google Veo.

Requires either:
- `GEMINI_API_KEY` environment variable (Google AI Studio), or
- `GOOGLE_CLOUD_PROJECT` + Application Default Credentials (Vertex AI — run `gcloud auth application-default login` first)
- Falls back to the active `gcloud config` project if no env var is set

## Usage

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/generate-meeting-video/scripts/generate_meeting_video.py OUTPUT --scenario SCENARIO_NAME --prompt 'optional custom prompt'"
```

### Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `output` | yes | Output MP4 file path (positional) |
| `--scenario` | yes | Scenario name (to find avatars directory) |
| `--prompt` | no | Custom animation prompt. Default: video conference call prompt |

### Example

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/generate-meeting-video/scripts/generate_meeting_video.py scripts/seeds/ellery/assets/meeting_recording.mp4 --scenario ellery"
```

## How It Works

1. **Composite** — Loads avatar PNGs from `scripts/seeds/{scenario}/avatars/`, arranges them in a video-call-style grid on a dark background, outputs a 1280×720 PNG
2. **Animate** — Uploads the composite to Google Veo (`veo-2.0-generate-001`) as an image-to-video input, polls for completion, downloads the MP4
