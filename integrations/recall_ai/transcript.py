from pydantic import BaseModel, Field

from app.models.accounts import User
from app.models.workspaces.meetings import Transcript, TranscriptLine, TranscriptParser
from config import logger


class RecallAITranscriptWords(BaseModel):
    text: str
    start_timestamp: float
    end_timestamp: float
    language: str | None = Field(default=None)
    confidence: float | None = Field(default=None)


class RecallAITranscriptChunk(BaseModel):
    words: list[RecallAITranscriptWords]
    speaker: str
    speaker_id: int | None = Field(default=None)
    language: str | None = Field(default=None)


class ProcessedRecallAITranscriptChunk(BaseModel):
    speaker: str
    text: str
    start_timestamp: float
    end_timestamp: float


class RecallAITranscript(BaseModel):
    chunks: list[RecallAITranscriptChunk] = Field(default_factory=list)

    @property
    def sorted_chunks(self):
        chunks_with_sorted_words: list[ProcessedRecallAITranscriptChunk] = []
        for chunk in self.chunks:
            if not chunk.words:
                continue

            valid_words = [word for word in chunk.words if word.text and word.text.strip()]
            if not valid_words:
                continue

            sorted_words = sorted(chunk.words, key=lambda x: x.start_timestamp)
            joined_text = " ".join([word.text for word in sorted_words if word.text])

            try:
                chunk_start = min([word.start_timestamp for word in sorted_words])
                chunk_end = max([word.end_timestamp for word in sorted_words])
            except ValueError as e:
                logger.warning(f"Failed to process timestamps for chunk: {e}")
                continue

            chunks_with_sorted_words.append(
                ProcessedRecallAITranscriptChunk(
                    speaker=chunk.speaker,
                    text=joined_text,
                    start_timestamp=chunk_start,
                    end_timestamp=chunk_end,
                )
            )

        return sorted(chunks_with_sorted_words, key=lambda x: x.start_timestamp)

    def combine_chunks(self):
        sorted_chunks = self.sorted_chunks
        if not sorted_chunks:
            return []

        combined_chunks: list[ProcessedRecallAITranscriptChunk] = []
        for chunk in sorted_chunks:
            if not chunk.text.strip():
                continue

            if combined_chunks and chunk.speaker == combined_chunks[-1].speaker:
                combined_chunks[-1].text += f" {chunk.text}"
                combined_chunks[-1].end_timestamp = chunk.end_timestamp
            else:
                combined_chunks.append(chunk)

        return combined_chunks

    def to_text(self) -> str:
        combined_chunks = self.combine_chunks()

        return "\n".join([f"{c.speaker}: {c.text}" for c in combined_chunks])


class RecallAITranscriptParser(TranscriptParser):
    @classmethod
    def is_correct_parser(cls, transcript: str) -> bool:
        try:
            RecallAITranscript.model_validate_json(transcript)
        except ValueError:
            return False

        return True

    @classmethod
    def parse(cls, transcript: str, user: User | None = None) -> Transcript:
        recall_transcript = RecallAITranscript.model_validate_json(transcript)

        if not recall_transcript.chunks:
            logger.error("RecallAI transcript has no chunks")
            return Transcript(lines=[])

        combined_chunks = recall_transcript.combine_chunks()
        if not combined_chunks:
            logger.error("No valid combined chunks produced")
            return Transcript(lines=[])

        parsed_lines: list[TranscriptLine] = []
        for index, chunk in enumerate(combined_chunks):
            if not chunk.text.strip():
                continue

            parsed_lines.append(
                TranscriptLine(
                    line_number=index,
                    speaker=chunk.speaker,
                    content=chunk.text,
                    start_time=chunk.start_timestamp,
                    end_time=chunk.end_timestamp,
                )
            )

        if not parsed_lines:
            logger.error("No valid lines parsed from RecallAI transcript")
            return Transcript(lines=[])

        logger.info(f"Recall AI transcript parsed with {len(parsed_lines)} lines")

        return Transcript(lines=parsed_lines)
