from app.helpers.html import render_email_html
from app.helpers.strings import html_to_plain_text
from app.presenters.mailbox_entries import MailboxEntryPresenter


def build_body_content(message_body_markdown: str) -> dict[str, str]:
    body_html = render_email_html(message_body_markdown) if message_body_markdown else ""
    body_plain = html_to_plain_text(body_html)
    preview = body_plain[:255] if body_plain else ""

    return {
        "body_markdown": message_body_markdown,
        "body_html": body_html,
        "body_plain": body_plain,
        "preview": preview,
    }


def format_sender_display(presenter: MailboxEntryPresenter) -> str:
    if presenter.original_sender and presenter.most_recent_sender and presenter.additional_sender_count == 0:
        return f"{presenter.original_sender.first_name}, {presenter.most_recent_sender.first_name}"
    elif presenter.original_sender and presenter.most_recent_sender and presenter.additional_sender_count > 0:
        return f"{presenter.original_sender.first_name}..{presenter.most_recent_sender.first_name}"
    elif presenter.original_sender:
        return presenter.original_sender.first_name
    else:
        return "Unknown"
