import re
from dataclasses import dataclass
from datetime import date, datetime

from app.models.accounts import User
from app.models.workspaces.meetings import Transcript, TranscriptLine, TranscriptParser


@dataclass
class FathomTranscriptLine:
    timestamp: float  # in seconds
    speaker: str
    content: str

    def __str__(self):
        return f"[{self.timestamp:.1f}s] {self.speaker}:\n  {self.content}\n"


class FathomTranscript(TranscriptParser):
    title: str
    recorded_on: date

    timestamp_pattern = re.compile(r"^@?(\d+):(\d+)\s*-\s*([^(]+)")
    bookmark_pattern = re.compile(r"BOOKMARK:.*? - WATCH: .*?  (.*)")
    annotation_pattern = re.compile(r"[A-Z ]+?:.*?WATCH.*")

    def __init__(self, title: str, recorded_on: date, lines: list[FathomTranscriptLine]):
        self.title = title
        self.recorded_on = recorded_on
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)

    @classmethod
    def is_correct_parser(cls, transcript: str):
        lines = transcript.split("\n")

        # Find the first timestamp line
        first_content_line_idx = next(
            (idx for idx, line in enumerate(lines) if cls.timestamp_pattern.match(line)), None
        )
        if first_content_line_idx is None:
            return False

        # If the phrase `VIEW RECORDING` is present before the first timestamp, it's likely a Fathom transcript
        if any("VIEW RECORDING" in line for line in lines[:first_content_line_idx]):
            return True

        if any("https://fathom.video" in line for line in lines[:first_content_line_idx]):
            return True

        return False

    @classmethod
    def parse(cls, content: str, user: User | None = None):
        if not cls.is_correct_parser(content):
            raise ValueError("Content does not appear to be a valid Fathom transcript")

        lines = content.split("\n")

        # First line always contains title and date. i.e. "Special Meeting - September 10"
        title, recorded_on = cls._get_title_and_date(lines[0])

        falthom_lines: list[FathomTranscriptLine] = []

        current_timestamp: float | None = None
        current_speaker: str | None = None
        current_lines: list[str] = []

        found_content = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if match := cls.timestamp_pattern.match(line):
                found_content = True
                # If we have accumulated content from previous speaker, save it
                if current_timestamp is not None and current_speaker is not None and current_lines:
                    falthom_lines.extend(
                        [
                            FathomTranscriptLine(
                                timestamp=current_timestamp,
                                speaker=current_speaker,
                                content=line,
                            )
                            for line in current_lines
                        ]
                    )
                    current_lines = []

                # Parse the new timestamp line
                minutes, seconds, speaker = match.groups()
                current_timestamp = cls._convert_timestamp_to_seconds(minutes, seconds)
                current_speaker = speaker.strip()
            elif not found_content:
                # Skip everything until we find the first timestamp
                continue
            elif match := cls.bookmark_pattern.match(line):
                # Bookmark sections contain the bookmarked content on the same line
                current_lines.append(match.group(1))
            elif match := cls.annotation_pattern.match(line):
                # All other annotations are ignored
                pass
            else:
                current_lines.append(line)

        # Don't forget to add the last segment
        if current_timestamp is not None and current_speaker is not None and current_lines:
            falthom_lines.extend(
                [
                    FathomTranscriptLine(
                        timestamp=current_timestamp,
                        speaker=current_speaker,
                        content=line,
                    )
                    for line in current_lines
                ]
            )

        transcript_lines = [
            TranscriptLine(line_number=i, speaker=line.speaker, content=line.content, start_time=line.timestamp)
            for i, line in enumerate(falthom_lines)
        ]

        return Transcript(title=title, recorded_on=recorded_on, lines=transcript_lines)

    @staticmethod
    def _convert_timestamp_to_seconds(minutes: str, seconds: str):
        return float(minutes) * 60 + float(seconds)

    @staticmethod
    def _get_title_and_date(line: str) -> tuple[str, date]:
        last_dash_index = line.rfind("-")
        if last_dash_index == -1:
            raise ValueError("Title and date not found in transcript")

        title = line[:last_dash_index].strip()
        date_string = line[last_dash_index + 1 :].strip()

        # Parse date, which does not include a year
        try:
            current_year = datetime.now().year
            date = datetime.strptime(f"{date_string} {current_year}", "%B %d %Y").date()
        except ValueError:
            raise ValueError("Date format not recognized")

        # If the date is in the future, it must be from the previous year
        if date > datetime.now().date():
            date = date.replace(year=date.year - 1)

        return title, date
