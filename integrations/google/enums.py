from enum import StrEnum


class GmailLabel(StrEnum):
    INBOX = "INBOX"
    SENT = "SENT"
    DRAFT = "DRAFT"
    SPAM = "SPAM"
    UNREAD = "UNREAD"
    TRASH = "TRASH"
