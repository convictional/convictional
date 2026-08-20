#!/usr/bin/env python3
import argparse
import asyncio
from uuid import UUID

from slugify import slugify

from app.models.workspaces.meetings import Meeting
from scripts.helpers import in_app_lifespan


async def main(meeting_id: str):
    meeting = await Meeting.get(id=UUID(meeting_id))

    if not meeting.processed_transcript:
        print(f"Meeting: {meeting.id} has no processed transcript.")

    print(f"Downloading transcript for meeting: {meeting.id}")

    fname = f"scripts/meetings/downloaded_transcripts/{slugify(meeting.title)}.txt"
    with open(fname, "w") as f:
        f.write(str(meeting.processed_transcript))

    print(f"Transcript saved to: {fname}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a meeting's transcript.")
    parser.add_argument("meeting_id", help="ID for a specific meeting.")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(in_app_lifespan(main(meeting_id=args.meeting_id)))
