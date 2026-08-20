# Channels Infrastructure

Real-time bidirectional communication via WebSockets using PostgreSQL NOTIFY/LISTEN for pub/sub.

## Overview

Channels enable real-time updates between server and client. Topics identify channels with signed IDs for security. Server broadcasts to topics; subscribed clients receive updates automatically. Client JS manages connections; server Python handles subscriptions and broadcasts.

### Example End-to-End Flow

1. User updates comment → Route saves to DB
2. Route broadcasts: `await topic.broadcast(comment_id=id)`
3. PostgreSQL NOTIFY reaches all server instances
4. Each server calls `@handle_stream` for subscribed sessions
5. Handler renders HTML, sends via WebSocket
6. `hx-channel` elements swap HTML automatically

## Core Architecture

```mermaid
flowchart TB
    subgraph Client["Client"]
        JS["ChannelsClient"]
        ConnMgr["ConnectionManager"]
        SubMgr["SubscriptionManager"]
    end

    subgraph Server["Server Process"]
        WS["WebSocket<br/>/channels"]
        Session["WebSocketSession"]
        Handlers["Handler Registries"]
    end

    subgraph Messaging["infra/messaging"]
        Adapter["PostgreSQLSubscriptionAdapter"]
        PG["PostgreSQL<br/>NOTIFY/LISTEN"]
        Cache["PostgreSQL<br/>CacheEntry table<br/>(large payloads)"]
    end

    JS --> ConnMgr
    JS --> SubMgr
    ConnMgr <--> WS
    WS --> Session
    Session <--> Handlers
    Handlers <--> Adapter
    Adapter <--> PG
    Adapter <--> Cache
```

## Multi-Server Broadcasting

```mermaid
flowchart TB
    subgraph Server1["Server Instance 1"]
        WS1["WebSocket Sessions"]
        Adapter1["PostgreSQL Adapter<br/>LISTEN tasks"]
    end

    subgraph Server2["Server Instance 2"]
        WS2["WebSocket Sessions"]
        Adapter2["PostgreSQL Adapter<br/>LISTEN tasks"]
    end

    subgraph PostgreSQL["PostgreSQL Database"]
        PG["NOTIFY/LISTEN"]
    end

    Code["Any Server:<br/>topic.broadcast()"]

    Code --> PG
    PG -->|notifies all| Adapter1
    PG -->|notifies all| Adapter2
    Adapter1 --> WS1
    Adapter2 --> WS2
```

All server instances share PostgreSQL NOTIFY/LISTEN, enabling broadcasts to reach clients connected to any server.

## Connection Lifecycle

```mermaid
sequenceDiagram
    participant Client
    participant WS as WebSocket
    participant Server as /channels
    participant Session

    Client->>WS: connect()
    WS->>Server: WebSocket handshake
    Server->>Server: Verify authentication

    alt Authenticated
        Server->>WS: Accept
        Server->>Session: Create WebSocketSession
        Session->>Session: Start _keep_alive() task
        Session->>Session: Start _message_loop() task
        WS->>Client: connected

        loop Every 30s
            Session->>WS: PING
            WS->>Client: PING
            Client->>WS: PONG
            WS->>Session: PONG
            Note over Session: Update last_pong_time
        end

        Note over Session: If no PONG for 90s<br/>close connection
    else Not Authenticated
        Server->>WS: Close (1008)
        WS->>Client: disconnected
    end
```

## Subscription Flow

```mermaid
sequenceDiagram
    participant Client
    participant Session as WebSocketSession
    participant Handler as subscribe_handler
    participant Adapter as PostgreSQLAdapter
    participant PG as PostgreSQL

    Client->>Session: SUBSCRIBE message<br/>{type, topic_id, params}
    Session->>Handler: execute subscribe handler

    Handler->>Handler: Verify authorization

    alt Authorized
        Handler->>Handler: channel.accept()
        Handler->>Session: Create ChannelSubscription
        Session->>Adapter: subscribe(topic, callback)
        Adapter->>PG: LISTEN "topic_name"
        PG-->>Adapter: listening
        Adapter-->>Session: subscribed
        Session->>Client: SUBSCRIPTION_CONFIRMED
    else Unauthorized
        Handler->>Session: channel.reject(error)
        Session->>Client: SUBSCRIPTION_REJECTED
    end
```

## Client Reconnection Strategy

```mermaid
flowchart TB
    Disconnect["Connection Lost"]
    Retry["Attempt Reconnect"]
    Backoff["Wait<br/>Exponential Backoff:<br/>1s → 2s → 4s → 8s → 16s → 30s"]
    MaxAttempts{"< 5 attempts?"}
    Reconnect["Connection Established"]
    Resubscribe["Resubscribe All Topics"]
    Hooks["Execute Reconnection Hooks"]
    GiveUp["Stop Retrying"]

    Disconnect --> Retry
    Retry --> MaxAttempts
    MaxAttempts -->|No| GiveUp
    MaxAttempts -->|Yes| Backoff
    Backoff --> Retry
    Retry -->|Success| Reconnect
    Reconnect --> Resubscribe
    Resubscribe --> Hooks
```

## Broadcast Flow

```mermaid
sequenceDiagram
    participant Route as Route/Job
    participant Topic
    participant PG as PostgreSQL
    participant Server1 as Server Instance 1
    participant Server2 as Server Instance 2
    participant Handler as @handle_stream
    participant WS as WebSocket
    participant Client

    Route->>Topic: topic.broadcast(comment_id=123)
    Topic->>PG: NOTIFY "email_thread_comments" '{"comment_id": 123}'

    par Notify all servers
        PG->>Server1: notification
        PG->>Server2: notification
    end

    Note over Server1,Server2: Each server processes independently

    Server1->>Handler: Execute broadcast_handlers["email_thread_comments"]
    Handler->>Handler: Render template with data
    Handler->>WS: Send DOMChangeMessage
    WS->>Client: {action: "outer_html", html: "...", target: "#comment_123"}
    Client->>Client: hx-channel swaps HTML
```

All servers receive every broadcast. Each server only sends to its own connected clients.

## Client Messages (on_receive)

Clients can send messages back to the server for bidirectional communication:

```mermaid
sequenceDiagram
    participant Client
    participant WS as WebSocket
    participant Session
    participant Handler as @router.on_receive
    participant Topic

    Client->>WS: {type: "TYPING", topic_id: "...", is_typing: true}
    WS->>Session: Route message
    Session->>Handler: Execute receive handler
    Handler->>Handler: Process message
    Handler->>Topic: topic.broadcast(is_typing=true)

    Note over Topic: Broadcast notifies all subscribers<br/>(see Broadcast Flow above)
```

Use `@router.on_receive(stream, MessageClass)` in `app/channels/` to handle client messages. Common pattern: process message, then broadcast result to all subscribers.

## Writing Channel Handlers

Channel modules live in `app/channels/`, one per feature. Each defines a `ChannelRouter` with handlers, and must be registered in `app/main.py` via `channels.include_router(...)` — a created-but-unregistered router fails silently.

| Decorator | Purpose | Signature |
|-----------|---------|-----------|
| `@router.on_subscribe(stream)` | Handle subscription requests | `async def handler(channel: Channel)` |
| `@router.on_unsubscribe(stream)` | Handle unsubscription/cleanup | `async def handler(channel: Channel)` |
| `@router.on_receive(stream, MessageType)` | Handle client-sent messages | `async def handler(channel: Channel, message: MessageType)` |
| `@router.on_keepalive(stream)` | Handle periodic keep-alive pings | `async def handler(channel: Channel)` |

A complete bidirectional example is `app/channels/email_thread_comments.py` (typing indicators). A broadcast-only example is `app/channels/workspace_events.py`.

### Authorization

Every subscribe handler must check authorization before calling `channel.accept()`:

```python
@router.on_subscribe("workspace_events")
async def workspace_events_subscribe(channel: Channel):
    if await is_workspace_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to workspace events.")
```

Shared helpers live in `app/channels/dependencies.py`: `is_workspace_authorized` (current user is a workspace collaborator), `is_current_user_authorized` (topic's `user_id` matches the session user), and `is_org_authorized`. For resource-specific checks, load the resource in the handler and reject if `collaboration.can_be_accessed_by(channel.current_user)` fails — see `app/channels/meetings.py`.

The only channels that may `accept()` unconditionally are genuinely public ones with no per-user data, like `version_refresh` in `app/channels/asset_reloading.py`.

### Trusted vs. untrusted parameters

`Channel` exposes two parameter sources, and the distinction is security-critical:

- **Topic params** are embedded in the signed topic ID generated server-side. Clients cannot tamper with them.
- **`channel.params`** is a free-form dict sent by the client. Never use it for authorization.

```python
# WRONG — params dict is client-controlled, any workspace_id can be sent
workspace_id = channel.params.get("workspace_id")

# RIGHT — get_param() checks signed topic params first
workspace_id = channel.get_param("workspace_id")
```

`channel.get_param(key)` prefers the signed topic params and only falls back to client params, so IDs used in authorization checks must come from the topic.

### Clean up state on unsubscribe

If a channel maintains shared state (typing indicators, presence), remove the user on unsubscribe — otherwise they linger after disconnecting:

```python
@router.on_unsubscribe("email_thread_comments")
async def email_thread_comments_unsubscribe(channel: Channel):
    email_thread_id = channel.get_param("email_thread_id")
    typing = Typing(scope_key=email_thread_scope_key(email_thread_id))
    typing_user_ids = await typing.remove_user(channel.current_user.id)
    await channel.topic.broadcast(typing_user_ids=typing_user_ids)
```

### Custom message types

Client-to-server messages are `ChannelMessage` subclasses. Add a value to `ChannelMessageType` in `config/enums.py`, then declare the class — the `_message_type` ClassVar registers it in the deserialization registry automatically:

```python
class MyCustomMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.MY_CUSTOM_TYPE
    my_field: str
```

Message types shared by multiple channels (e.g. `TypingMessage`) live in `app/channels/dependencies.py`.

### Broadcasting from routers, jobs, and models

Any server code can broadcast by constructing a `Topic` with the same stream name and params the channel was subscribed with — params are part of the topic identity, so omitting one (e.g. `workspace_id`) silently broadcasts to a different topic nobody is listening on:

```python
from infra.messaging import Topic

topic = Topic("workspace_events", workspace_id=str(workspace.id))
await topic.broadcast(action="comment_added", comment_id=str(comment.id))
```

### Code references

- Channel/router base classes: `app/channels/base.py`
- Authorization helpers and shared messages: `app/channels/dependencies.py`
- Topic and pub/sub: `infra/messaging.py`
- WebSocket endpoint: `app/routers/channels.py`
- Router registration: `app/main.py`
- Client side: `app/javascript/channels/` (client, subscription manager, HTMX extension, Yjs provider)
