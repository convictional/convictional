"""
Type definitions for Google API responses.

These TypedDicts define the structure of responses from Google's Gmail and People APIs.
They match the official API specifications and use camelCase field names as returned by Google.

References:
- Gmail API: https://developers.google.com/workspace/gmail/api/reference/rest
- People API: https://developers.google.com/people/api/rest
"""

from typing import Any, NotRequired, TypedDict, cast

from infra.email import EmailHeaders

#
# Gmail API Types
#


class GmailProfile(TypedDict):
    emailAddress: str
    messagesTotal: int
    threadsTotal: int
    historyId: str


class GmailWatchResponse(TypedDict):
    historyId: str
    expiration: str


class GmailMessagePartHeader(TypedDict):
    name: str
    value: str


def gmail_headers_to_email_headers(headers: list[GmailMessagePartHeader]) -> EmailHeaders:
    """Convert Gmail API headers to EmailHeaders.

    This provides type-safe conversion from Gmail API response format to our internal EmailHeaders format.
    """
    return EmailHeaders(cast(list[dict[str, str]], headers))


class GmailMessagePartBody(TypedDict):
    attachmentId: NotRequired[str]
    size: NotRequired[int]
    data: NotRequired[str]


class GmailMessagePart(TypedDict):
    """
    Recursive structure representing a MIME message part.

    Can contain nested parts for multipart messages (e.g., text + attachments).
    """

    partId: str
    mimeType: str
    filename: NotRequired[str]
    headers: list[GmailMessagePartHeader]
    body: NotRequired[GmailMessagePartBody]
    parts: NotRequired[list["GmailMessagePart"]]


class GmailMessage(TypedDict):
    id: str
    threadId: str
    labelIds: NotRequired[list[str]]
    snippet: NotRequired[str]
    historyId: NotRequired[str]
    internalDate: NotRequired[str]
    payload: NotRequired[GmailMessagePart]
    sizeEstimate: NotRequired[int]
    raw: NotRequired[str]


class GmailThread(TypedDict):
    id: str
    snippet: NotRequired[str]
    historyId: NotRequired[str]
    messages: NotRequired[list[GmailMessage]]


class GmailThreadListResponse(TypedDict):
    threads: NotRequired[list[GmailThread]]
    nextPageToken: NotRequired[str]
    resultSizeEstimate: NotRequired[int]


class GmailHistoryMessage(TypedDict):
    id: str
    threadId: NotRequired[str]
    labelIds: NotRequired[list[str]]


class GmailHistoryMessageAdded(TypedDict):
    message: GmailHistoryMessage


class GmailHistoryMessageDeleted(TypedDict):
    message: GmailHistoryMessage


class GmailHistoryLabelsAdded(TypedDict):
    message: GmailHistoryMessage
    labelIds: list[str]


class GmailHistoryLabelsRemoved(TypedDict):
    message: GmailHistoryMessage
    labelIds: list[str]


class GmailHistory(TypedDict):
    id: str
    messages: NotRequired[list[GmailMessage]]
    messagesAdded: NotRequired[list[GmailHistoryMessageAdded]]
    messagesDeleted: NotRequired[list[GmailHistoryMessageDeleted]]
    labelsAdded: NotRequired[list[GmailHistoryLabelsAdded]]
    labelsRemoved: NotRequired[list[GmailHistoryLabelsRemoved]]


class GmailHistoryListResponse(TypedDict):
    history: NotRequired[list[GmailHistory]]
    historyId: NotRequired[str]
    nextPageToken: NotRequired[str]


class GmailAttachment(TypedDict):
    data: str
    size: NotRequired[int]
    headers: NotRequired[list[dict[str, str]]]


#
# People API Types
#


class PeopleName(TypedDict):
    displayName: NotRequired[str]
    familyName: NotRequired[str]
    givenName: NotRequired[str]
    displayNameLastFirst: NotRequired[str]
    unstructuredName: NotRequired[str]


class PeopleEmailAddress(TypedDict):
    value: NotRequired[str]
    type: NotRequired[str]
    formattedType: NotRequired[str]


class PeoplePhoto(TypedDict):
    url: NotRequired[str]
    default: NotRequired[bool]


class PeoplePerson(TypedDict):
    resourceName: NotRequired[str]
    etag: NotRequired[str]
    names: NotRequired[list[PeopleName]]
    emailAddresses: NotRequired[list[PeopleEmailAddress]]
    photos: NotRequired[list[PeoplePhoto]]
    metadata: NotRequired[dict[str, Any]]


class PeopleConnectionsListResponse(TypedDict):
    connections: NotRequired[list[PeoplePerson]]
    nextPageToken: NotRequired[str]
    nextSyncToken: NotRequired[str]
    totalPeople: NotRequired[int]
    totalItems: NotRequired[int]


class PeopleOtherContactsListResponse(TypedDict):
    otherContacts: NotRequired[list[PeoplePerson]]
    nextPageToken: NotRequired[str]
    nextSyncToken: NotRequired[str]
    totalSize: NotRequired[int]
