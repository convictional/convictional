# Channel Backends

This directory contains backend implementations for the channels client.

## WebsocketBackend

This backend uses WebSockets directly to communicate with the server. It establishes one WebSocket connection per tab.

```
                        ┌────────────┐
                        │   Server   │
                        └────────────┘
                              ▲▲▲
                   WebSockets │││
           ┌──────────────────┘│└──────────────────┐
           │                   │                   │
┌──────────┼───────────────────┼───────────────────┼─────────┐
│┌─────────▼────────┐┌─────────▼────────┐┌─────────▼────────┐│
││ ┌──────────────┐ ││ ┌──────────────┐ ││ ┌──────────────┐ ││
││ │  WebSocket   │ ││ │  WebSocket   │ ││ │  WebSocket   │ ││
││ │   Backend    │ ││ │   Backend    │ ││ │   Backend    │ ││
││┌┴──────────────┴┐││┌┴──────────────┴┐││┌┴──────────────┴┐││
│││Channels Client ││││Channels Client ││││Channels Client │││
││└────────────────┘││└────────────────┘││└────────────────┘││
││     Page/Tab     ││     Page/Tab     ││     Page/Tab     ││
│└──────────────────┘└──────────────────┘└──────────────────┘│
│                          Browser                           │
└────────────────────────────────────────────────────────────┘
```
