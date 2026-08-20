---
description: Generate a portrait avatar for a demo seed character using Gemini image generation
---

# Generate Avatar

Generate a single portrait avatar image using the Gemini image generation API. Output is a 256x256 PNG.

Requires either:
- `GEMINI_API_KEY` environment variable (Google AI Studio), or
- `GOOGLE_CLOUD_PROJECT` + Application Default Credentials (Vertex AI — run `gcloud auth application-default login` first)
- Falls back to the active `gcloud config` project if no env var is set

## Usage

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/generate-avatar/scripts/generate_avatars.py OUTPUT --description 'DESCRIPTION' --style 'STYLE'"
```

### Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `output` | yes | Output PNG file path (positional) |
| `--description` | yes | What to generate — the subject of the portrait |
| `--style` | no | Art style prefix. Default is a tight head-and-shoulders corporate headshot for consistency with existing scenarios. Override when a scenario wants a different aesthetic (e.g., puppet, painting). |

### Example

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/generate-avatar/scripts/generate_avatars.py scripts/seeds/meridian_gis/avatars/nadia.png --description 'Nadia, a CEO and former wildfire researcher, impatient and visionary' --style 'Jim Henson style puppet portrait with felt and foam construction, expressive glass eyes, visible stitching'"
```

## Generating All Avatars for a Scenario

Read the story's Cast of Characters and Avatar Style sections, then call this script once per character. Run calls sequentially to avoid rate limits.
