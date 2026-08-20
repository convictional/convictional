from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from app.models.collaboration.workspace import LinkPreview
from app.models.workspaces.posts import Post, PostComment
from app.presenters.posts import PostCommentPresenter, PostPresenter
from config.enums import LinkPreviewStatus, LinkPreviewType


def _comment_presenter(content: str, preview_url: str | None = None) -> PostCommentPresenter:
    comment = PostComment(content=content)
    link_preview = None
    if preview_url:
        link_preview = LinkPreview(url=preview_url, status=LinkPreviewStatus.READY, type=LinkPreviewType.LINK)

    presenter = PostCommentPresenter(comment, reaction_users=[])
    presenter.replies = []
    presenter.link_preview = link_preview
    return presenter


def test_content_without_preview_url_strips_plain_url():
    presenter = _comment_presenter("Check this out https://example.com/article", "https://example.com/article")
    assert presenter.content_without_preview_url == "Check this out"


def test_content_without_preview_url_preserves_markdown_link():
    presenter = _comment_presenter("[Read more](https://example.com/article)", "https://example.com/article")
    assert presenter.content_without_preview_url == "[Read more](https://example.com/article)"


def test_content_without_preview_url_preserves_markdown_link_with_surrounding_text():
    presenter = _comment_presenter(
        "Hey check this [Read more](https://example.com/article) for context",
        "https://example.com/article",
    )
    expected = "Hey check this [Read more](https://example.com/article) for context"
    assert presenter.content_without_preview_url == expected


def test_content_without_preview_url_no_preview():
    presenter = _comment_presenter("Just some text https://example.com")
    assert presenter.content_without_preview_url == "Just some text https://example.com"


def test_content_without_preview_url_with_query_params():
    url = "https://example.com/article?utm_source=test&id=123"
    presenter = _comment_presenter(f"See {url}", url)
    assert presenter.content_without_preview_url == "See"


def test_content_without_preview_url_strips_autolinked_url():
    url = "https://example.com/article"
    presenter = _comment_presenter(f"[{url}]({url})", url)
    assert presenter.content_without_preview_url == ""


def test_preview_text_renders_markdown_to_single_line_plaintext():
    presenter = _comment_presenter("# Heading\n\n**Bold** and [a link](https://example.com)")
    assert presenter.preview_text == "Heading Bold and a link"


def test_preview_text_strips_preview_url_before_rendering():
    presenter = _comment_presenter(
        "Read this https://example.com/article it's great",
        "https://example.com/article",
    )
    assert presenter.preview_text == "Read this it's great"


def _comment_presenter_with_created_at(created_at: datetime) -> PostCommentPresenter:
    comment = PostComment(id=uuid4(), created_at=created_at)
    presenter = PostCommentPresenter(comment, reaction_users=[])
    presenter.replies = []
    return presenter


def test_post_presenter_comment_count_and_last_commented_at():
    older = datetime(2024, 1, 1, tzinfo=UTC)
    newer = datetime(2024, 1, 2, tzinfo=UTC)

    comment1 = _comment_presenter_with_created_at(older)
    comment2 = _comment_presenter_with_created_at(newer)
    comment1.replies = [_comment_presenter_with_created_at(newer)]

    presenter = PostPresenter(
        model=cast(Post, None), original_comment=None, top_level_comments=[comment1, comment2], whats_new=None
    )

    assert presenter.comment_count == 3  # 2 top-level + 1 reply
    assert presenter.last_commented_at == newer
