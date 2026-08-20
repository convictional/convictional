from datetime import UTC, datetime
from uuid import uuid4

from app.models.commands import ResearchQuestion
from config.enums import ResearchSource


def test_research_question_status_pending():
    """Status is PENDING when research_id is None"""
    question = ResearchQuestion(
        body="Test question",
        sources=[ResearchSource.INTERNAL],
        creator_id=uuid4(),
        response_completed_at=None,
    )
    question.research_id = None
    assert question.status.is_pending
    assert not question.status.is_started
    assert not question.status.is_completed


def test_research_question_status_started():
    """Status is STARTED when research_id is set but response not completed"""
    question = ResearchQuestion(
        body="Test question",
        sources=[ResearchSource.INTERNAL],
        creator_id=uuid4(),
        response_completed_at=None,
    )
    question.research_id = uuid4()
    assert not question.status.is_pending
    assert question.status.is_started
    assert not question.status.is_completed


def test_research_question_status_completed():
    """Status is COMPLETED when response_completed_at is set"""
    question = ResearchQuestion(
        body="Test question",
        sources=[ResearchSource.INTERNAL],
        creator_id=uuid4(),
        response_completed_at=datetime.now(UTC),
    )
    question.research_id = uuid4()
    assert not question.status.is_pending
    assert not question.status.is_started
    assert question.status.is_completed
