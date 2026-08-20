import re

from app.models.accounts import User
from app.models.workspaces.meetings import Transcript, TranscriptLine, TranscriptParser


class GranolaTranscript(TranscriptParser):
    sample_line_count = 10
    min_valid_lines = 8
    re_pattern = re.compile(r"^(Me|Them(?=\: ))(.*)$")

    @classmethod
    def is_correct_parser(cls, transcript: str):
        # It's not clear whether the first line always contains a speaker name.
        lines = transcript.split("\n")
        n_valid_lines = sum(1 for line in lines[: cls.sample_line_count] if GranolaTranscript.re_pattern.match(line))
        if (n_valid_lines >= cls.min_valid_lines) or (len(lines) < cls.min_valid_lines and n_valid_lines > 0):
            return True
        return False

    @staticmethod
    def parse_line(line: str) -> tuple[str | None, str]:
        match = GranolaTranscript.re_pattern.match(line)
        if match:
            speaker, content = match.groups()
            return speaker, content
        return None, line

    @staticmethod
    def iter_lines(content: str):
        for line in content.split("\n"):
            if line.strip() == "":
                continue
            yield GranolaTranscript.parse_line(line.strip())

    @staticmethod
    def translate_speaker(speaker: str | None, user: User | None) -> str | None:
        if speaker is None:
            return None

        if speaker == "Me" and user:
            return user.display_name

        return speaker

    @classmethod
    def parse(cls, content: str, user: User | None = None):
        if not cls.is_correct_parser(content):
            raise ValueError("Content does not appear to be a valid Granola transcript")

        return Transcript(
            lines=[
                TranscriptLine(
                    line_number=i,
                    speaker=cls.translate_speaker(speaker, user),
                    content=content,
                )
                for i, (speaker, content) in enumerate(cls.iter_lines(content))
            ]
        )
