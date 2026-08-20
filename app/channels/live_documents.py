import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pycrdt import (
    Awareness,
    TransactionEvent,
    YSyncMessageType,
    create_sync_message,
    create_update_message,
    handle_sync_message,
)

from app.channels.base import BaseChannelMessage, Channel, ChannelMessage
from app.models.collaboration.live import LiveDocument, LiveDocumentUpdate
from config import logger
from config.enums import ChannelMessageType
from infra.messaging import Topic, subscribe, unsubscribe


class LiveDocumentSyncMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.LIVE_DOCUMENT_SYNC
    data: str

    @classmethod
    def from_bytes(cls, topic: Topic, data: bytes):
        return cls(topic_stream=topic.stream, topic_params=topic.params, data=base64.b64encode(data).decode("utf-8"))

    @property
    def data_bytes(self) -> bytes:
        return base64.b64decode(self.data)


class YjsAwarenessMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.LIVE_DOCUMENT_AWARENESS
    data: str

    @classmethod
    def from_bytes(cls, topic: Topic, data: bytes):
        return cls(topic_stream=topic.stream, topic_params=topic.params, data=base64.b64encode(data).decode("utf-8"))


REMOTE_ORIGIN = "remote-server"


@dataclass
class SharedDocument:
    document: LiveDocument
    topic: Topic
    awareness: Awareness
    should_stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _ready: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _sync_queue: asyncio.Queue[tuple[LiveDocumentSyncMessage, Channel]] = field(
        default_factory=asyncio.Queue, init=False
    )
    subscribers: list[Channel] = field(default_factory=list, init=False)
    _listen_task: asyncio.Task | None = field(default=None, init=False)

    async def start(self):
        await subscribe(self.topic, self._handle_server_sync_update)
        self._listen_task = asyncio.create_task(self._listen())

    async def stop_session(self) -> None:
        await unsubscribe(self.topic, self._handle_server_sync_update)
        self.should_stop.set()
        if self._listen_task:
            await self._listen_task
            self._listen_task = None

    def add_subscriber(self, channel: Channel) -> None:
        if channel not in self.subscribers:
            self.subscribers.append(channel)

    def remove_subscriber(self, channel: Channel) -> None:
        if channel in self.subscribers:
            self.subscribers.remove(channel)

    @property
    def has_subscribers(self) -> bool:
        return len(self.subscribers) > 0

    async def _listen(self):
        tasks = asyncio.TaskGroup()
        async with tasks:

            def observe_document_change(event: TransactionEvent):
                if event.transaction.origin() is not None:  # type: ignore[attr-defined]
                    return
                tasks.create_task(self.handle_document_change(event))

            def observe_awareness_change(type: str, changes: tuple[dict[str, Any], Any]):
                tasks.create_task(self.handle_awareness_change(type, changes))

            document_subscription = self.document.observe(observe_document_change)
            awareness_subscription = self.awareness.observe(observe_awareness_change)
            self._ready.set()

            try:
                while not self.should_stop.is_set():
                    try:
                        sync_message, channel = await asyncio.wait_for(self._sync_queue.get(), timeout=1.0)
                        await self._process_sync_message(sync_message, channel)
                    except TimeoutError:
                        continue
            except Exception:
                logger.exception(f"Error in listener for topic {self.topic.name}")
                raise
            finally:
                self.document.unobserve(document_subscription)
                self.awareness.unobserve(awareness_subscription)

    async def handle_document_change(self, event: TransactionEvent):
        await self.topic.broadcast(
            **LiveDocumentSyncMessage.from_bytes(self.topic, create_update_message(event.update)[1:]).model_dump()
        )
        await LiveDocumentUpdate.create(
            topic_name=self.topic.name,
            update_data=event.update,
        )

    async def handle_awareness_change(self, type: str, changes: tuple[dict[str, Any], Any]):
        if type != "update" or changes[1] != "local":
            return

        updated_clients = [v for value in changes[0].values() for v in value]
        update = self.awareness.encode_awareness_update(updated_clients)
        await self.topic.broadcast(**YjsAwarenessMessage.from_bytes(self.topic, update).model_dump())

    async def handle_sync_message(self, message: LiveDocumentSyncMessage, channel: Channel):
        await self._sync_queue.put((message, channel))

    async def _process_sync_message(self, message: LiveDocumentSyncMessage, channel: Channel):
        message_type = message.data_bytes[0]
        response = handle_sync_message(message.data_bytes, self.document)

        if response:
            await channel.session.send(LiveDocumentSyncMessage.from_bytes(channel.topic, response[1:]))

        # When client sends SyncStep1, also send our SyncStep1 back so client
        # responds with SyncStep2 containing any updates we're missing (e.g. offline edits)
        if message_type == YSyncMessageType.SYNC_STEP1:
            server_sync_step1 = create_sync_message(self.document)
            await channel.session.send(LiveDocumentSyncMessage.from_bytes(channel.topic, server_sync_step1[1:]))

    async def _handle_server_sync_update(self, data: dict[str, Any]) -> None:
        message = BaseChannelMessage.from_dict(data)
        if isinstance(message, LiveDocumentSyncMessage):
            async with self._lock:
                with self.document.transaction(origin=REMOTE_ORIGIN):
                    handle_sync_message(message.data_bytes, self.document)


@dataclass
class DocumentManager:
    lock: asyncio.Lock = asyncio.Lock()
    documents: dict[Topic, SharedDocument] = field(default_factory=dict)

    async def _get_or_create_session(self, channel: Channel) -> SharedDocument:
        async with self.lock:
            if channel.topic not in self.documents:
                document = await LiveDocument.for_topic(channel.topic)
                awareness = Awareness(document)
                shared_document = SharedDocument(document=document, topic=channel.topic, awareness=awareness)
                await shared_document.start()
                self.documents[channel.topic] = shared_document

            return self.documents[channel.topic]

    async def subscribe(self, channel: Channel):
        document = await self._get_or_create_session(channel)
        document.add_subscriber(channel)
        await channel.accept()

    async def unsubscribe(self, channel: Channel):
        async with self.lock:
            document = self.documents.get(channel.topic)
            if document:
                document.remove_subscriber(channel)

                # If no more channels are subscribed, clean up the session
                if not document.has_subscribers:
                    document = self.documents.pop(channel.topic, None)
                    if document:
                        await document.stop_session()

    async def sync_message(self, channel: Channel, message: LiveDocumentSyncMessage):
        document = await self._get_or_create_session(channel)
        await document.handle_sync_message(message, channel)

    async def awareness_message(self, channel: Channel, message: YjsAwarenessMessage):
        await channel.topic.broadcast(**message.model_dump())


document_manager = DocumentManager()
