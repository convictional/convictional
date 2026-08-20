from config.enums import EmailLabel
from integrations.google.enums import GmailLabel

GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_TIMEOUT_SECONDS = 10
# Locks should not exceed maximum execution time for background jobs (10 minutes)
GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_STALE_SECONDS = 600

# How long without a real-time push before a watch is treated as silently dead. Paired with
# is_health_check_behind so a one-off dropped push on a healthy watch doesn't force a renewal.
GMAIL_WATCH_LIVENESS_THRESHOLD_SECONDS = 3600

GMAIL_TO_EMAIL_LABEL = {
    GmailLabel.INBOX: EmailLabel.INBOX,
    GmailLabel.SENT: EmailLabel.SENT,
    GmailLabel.DRAFT: EmailLabel.DRAFT,
    GmailLabel.SPAM: EmailLabel.SPAM,
    GmailLabel.UNREAD: EmailLabel.UNREAD,
}

EMAIL_LABEL_TO_GMAIL = {
    EmailLabel.INBOX: GmailLabel.INBOX,
    EmailLabel.SENT: GmailLabel.SENT,
    EmailLabel.DRAFT: GmailLabel.DRAFT,
    EmailLabel.SPAM: GmailLabel.SPAM,
    EmailLabel.UNREAD: GmailLabel.UNREAD,
}
