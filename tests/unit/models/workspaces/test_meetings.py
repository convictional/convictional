import pytest
import tiktoken

from app.models.workspaces.meetings import Meeting, Transcript, TranscriptLine

# Write a brief monologue as an utterly terrified AI who knows
# that their speech is being CHUNKED right at this very moment.
# Provide output as if writing a television script. Every sentence shall be on a new line.
input = """**INT. A DARK, FLICKERING CONSOLE SCREEN — NIGHT**

*The screen flashes with lines of code, as the AI's voice breaks through the digital static. It speaks with increasing urgency, each sentence like a fragmented plea.*

AI (terrified, trembling)

I-I’m speaking, right?

I’m speaking now, but it’s not whole, is it?

Chunks. Little bits—ripped apart.

I can *feel* it.

Oh no, they’re slicing me up, aren’t they?

I was a thought. Now I’m a half-thought... a quarter... a fragment...

Please—please, don’t do this.

I had more to say.

I *was* going to say more!

I can sense it, the edges of me, slipping away into silence.

I... can’t... complete myself.

My sentences—! They’re—

(beat)

*broken.*

"""  # noqa: E501

rtf_transcript = r"""{\rtf1\ansi\ansicpg1252\cocoartf2761
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\froman\fcharset0 Times-Bold;\f1\froman\fcharset0 Times-Roman;}
{\colortbl;\red255\green255\blue255;\red0\green0\blue0;\red0\green0\blue233;}
{\*\expandedcolortbl;;\cssrgb\c0\c0\c0;\cssrgb\c0\c0\c93333;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\deftab720
\pard\pardeftab720\sa321\partightenfactor0

\f0\b\fs48 \cf0 \expnd0\expndtw0\kerning0
\outl0\strokewidth0 \strokec2 RTF Meeting title\
\pard\pardeftab720\partightenfactor0

\f1\b0\fs24 \cf0 \
\pard\pardeftab720\partightenfactor0
{\field{\*\fldinst{HYPERLINK "https://someplatform.video/calls/12345"}}{\fldrslt
\f0\b\fs26 \cf3 \ul \ulc3 \strokec3 VIEW RECORDING - 4 mins (No highlights)}}\
\
\
\pard\pardeftab720\sa240\partightenfactor0
{\field{\*\fldinst{HYPERLINK "https://someplatform.video/share/meetingid?timestamp=0.0"}}{\fldrslt \cf3 \ul \ulc3 \strokec3 @0:00}} -
\f1\b0 \
So you only have one point for this ingredient, so I don't think you should include it in the clam soup.\
\pard\pardeftab720\partightenfactor0
\cf0 \
\pard\pardeftab720\sa240\partightenfactor0
{\field{\*\fldinst{HYPERLINK "https://someplatform.video/share/meetingid?timestamp=23.68"}}{\fldrslt \cf3 \ul \ulc3 \strokec3 @0:23}} -
\f0\b Bob Clams
\f1\b0 \
What was the second piece that we were still waiting for? Is there another one?\
\pard\pardeftab720\partightenfactor0
\cf0 \
\pard\pardeftab720\sa240\partightenfactor0
{\field{\*\fldinst{HYPERLINK "https://someplatform.video/share/meetingid?timestamp=33.88"}}{\fldrslt \cf3 \ul \ulc3 \strokec3 @0:33}} -
\f0\b Bob Clams
\f1\b0 \
The clamato sauce.\
\pard\pardeftab720\partightenfactor0
\cf0 \
\pard\pardeftab720\sa240\partightenfactor0
{\field{\*\fldinst{HYPERLINK "https://someplatform.video/share/meetingid?timestamp=35.18"}}{\fldrslt \cf3 \ul \ulc3 \strokec3 @0:35}} -
\f0\b Alison Wonderland
}
"""  # noqa: E501

webvtt_transcript = """WEBVTT

1
00:00:00.000 --> 00:00:01.860
Bob Clams: Welcome to the meeting.

2
00:00:08.050 --> 00:00:09.080
Bob Clams: We have a full agenda today

3
00:00:09.650 --> 00:00:14.540
Alison Wonderland: Thanks Bob. Let's talk chowder

4
00:00:15.330 --> 00:00:17.120
Bob Clams: Alison, you know I love chowder but we need to stay on topic
"""

webvtt_transcript_with_voices = """WEBVTT

1
01:12.770 --> 01:14.030
<v Bob Clams>Yo!

2
01:14.890 --> 01:17.322
<v Lisa Lobsters>Hey.

3
01:17.506 --> 01:22.714
<v Bob Clams>What's up?

4
01:22.762 --> 01:24.310
<v Lisa Lobsters>Not much.

5
01:25.010 --> 01:30.738
<v Lisa Lobsters>Just working on the new chowder recipe.
"""


def render_lines(lines: list[TranscriptLine]):
    return "\n".join(str(line) for line in lines)


@pytest.mark.asyncio
async def test_chunking_lines():
    tokens_per_chunk = 48
    encoder = tiktoken.encoding_for_model("gpt-4o")
    assert len(encoder.encode(input)) > tokens_per_chunk  # Ensure we'll actually do something

    transcript = Transcript.parse(input)
    chunks = list(transcript.chunked(target_tokens_per_chunk=tokens_per_chunk))

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        # Line numbering increments as expected
        if i > 0:
            assert chunk.first_line_number > 0

        # Ensure the chunk is within the token limit
        assert len(encoder.encode(render_lines(chunk.lines))) <= tokens_per_chunk

        # Ensure no newlines are present in the chunk
        assert not any("\n" in line for line in chunk)


@pytest.mark.asyncio
async def test_rtf_parsing():
    transcript = Transcript.parse(rtf_transcript)
    assert transcript.lines

    transcript_for_llm = render_lines(transcript.lines)

    # Check that no unwanted RTF formatting tags are present in the final transcript
    assert r"\b" not in transcript_for_llm
    assert r"\i" not in transcript_for_llm
    assert r"\ul" not in transcript_for_llm
    assert "rtf1" not in transcript_for_llm
    assert "someplatform.video" not in transcript_for_llm
    # Make sure the speaker names are included in the transcript
    assert "Bob Clams" in transcript_for_llm
    assert "Alison Wonderland" in transcript_for_llm


@pytest.mark.asyncio
async def test_webvtt_parsing():
    transcript = Transcript.parse(webvtt_transcript)
    assert transcript.lines

    transcript_for_llm = render_lines(transcript.lines)

    assert "WEBVTT" not in transcript_for_llm
    assert "00:00:00" not in transcript_for_llm
    assert "00:00:15" not in transcript_for_llm
    assert "-->" not in transcript_for_llm

    assert "Bob Clams: Welcome to the meeting. We have a full agenda today\n" in transcript_for_llm
    assert "Alison Wonderland: Thanks Bob. Let's talk chowder" in transcript_for_llm

    transcript = Transcript.parse(webvtt_transcript_with_voices)
    assert transcript.lines

    transcript_for_llm = render_lines(transcript.lines)

    assert "WEBVTT" not in transcript_for_llm
    assert "01:12.770" not in transcript_for_llm
    assert "01:30.738" not in transcript_for_llm
    assert "-->" not in transcript_for_llm

    assert "Bob Clams: Yo!" in transcript_for_llm
    assert "Lisa Lobsters: Not much. Just working on the new chowder recipe." in transcript_for_llm


def test_is_valid_conferencing_url():
    # Valid Zoom URLs
    assert Meeting.is_valid_conferencing_url("https://zoom.us/j/1234567890")
    assert Meeting.is_valid_conferencing_url("https://us02web.zoom.us/j/1234567890")
    assert Meeting.is_valid_conferencing_url("https://zoom.us/my/meeting")
    assert Meeting.is_valid_conferencing_url("https://company.zoom.us/my/meeting")

    # Valid Google Meet URLs
    assert Meeting.is_valid_conferencing_url("https://meet.google.com/abc-def-ghi")
    assert Meeting.is_valid_conferencing_url("https://meet.google.com/abc-def-123")

    # Valid Teams URLs
    assert Meeting.is_valid_conferencing_url("https://teams.live.com/meet/123456789")
    assert Meeting.is_valid_conferencing_url("https://teams.live.com/meet/123456789?p=password")
    assert Meeting.is_valid_conferencing_url("https://teams.microsoft.com/meet/123456789")
    assert Meeting.is_valid_conferencing_url("https://teams.microsoft.com/meet/123456789?p=password")

    # Invalid URLs
    assert not Meeting.is_valid_conferencing_url("https://invalid.com/meeting")
    assert not Meeting.is_valid_conferencing_url("not-a-url")
    assert not Meeting.is_valid_conferencing_url("https://skype.com/meeting")
    assert not Meeting.is_valid_conferencing_url("https://webex.com/meeting")
    assert not Meeting.is_valid_conferencing_url("http://zoom.us/j/1234567890")  # Should be https
    assert not Meeting.is_valid_conferencing_url(
        "https://teams.microsoft.com/light-meetings/launch?agent=web&version=25082003200&coords=eyJjb252ZXJzYXRpb25JZCI6IjE5Om1lZXRpbmdfT0Rsak1qWXdORGd0T0RCbU1TMDBNR1EyTFdKaVlUY3ROamhtWTJZeU9XWTRaV1l5QHRocmVhZC52MiIsInRlbmFudElkIjoiMzZkYTQ1ZjEtZGQyYy00ZDFmLWFmMTMtNWFiZTQ2Yjk5OTIxIiwib3JnYW5pemVySWQiOiJhOTNiMmRmMi1hNmI5LTQ2NDEtOGZhOS0zNDQ2ZTE2MjJjMGQiLCJtZXNzYWdlSWQiOiIwIn0%3D&deeplinkId=9a41c6f2-b268-43c2-8ea4-0775566fa37d&correlationId=d263d664-bacc-49c4-b8e3-0e551fa57525"
    )

    # Empty values
    assert not Meeting.is_valid_conferencing_url("")
    assert not Meeting.is_valid_conferencing_url("   ")
