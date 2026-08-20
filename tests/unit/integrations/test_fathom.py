from app.models.workspaces.meetings import Transcript
from config import settings
from integrations.fathom import FathomTranscript


def test_fathom_parser():
    for filename in ["fathom-1.txt", "fathom-2.txt", "fathom-3.txt", "fathom-4.txt"]:
        with open(settings.root / "tests" / "fixtures" / filename) as f:
            transcript = FathomTranscript.parse(f.read())
            assert isinstance(transcript, Transcript)

            # Timestamps exist
            assert all(isinstance(line.start_time, float) for line in transcript.lines)

            # Timestamps only go up
            for i, line in enumerate(transcript.lines):
                if line.start_time is not None:
                    assert isinstance(line.start_time, float)
                    assert line.start_time >= 0
                    previous_line_end_time = transcript.lines[i - 1].end_time if i > 0 else None
                    if i > 0 and previous_line_end_time is not None:
                        assert line.start_time > previous_line_end_time

            # Speakers exist
            assert all(line.speaker for line in transcript.lines)

            # Content exists
            assert all(line.content for line in transcript.lines)

            # Title and date extraction
            assert transcript.title
            assert transcript.recorded_on
