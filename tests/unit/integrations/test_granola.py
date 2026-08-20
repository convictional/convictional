from app.models.workspaces.meetings import Transcript
from integrations.granola import GranolaTranscript

input = """This first line of dialog is ambiguously attributed.
Me: Who knows who said that?
Them: I don't know, but it was a good line.
Me: I think it was me.
Them: I think it was you too.
Me: I think it was me too.
Them: I think it was you too.
Me: I think it was you too.
Them: I think it was you too.
"""  # Thanks, Copilot!


def test_fathom_parser():
    transcript = GranolaTranscript.parse(input)
    assert isinstance(transcript, Transcript)

    # Speakers exist when they should
    assert all(line.speaker for line in transcript.lines[1:])

    # Content exists
    assert all(line.content for line in transcript.lines)
