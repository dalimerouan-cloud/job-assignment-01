from __future__ import annotations

import asyncio
from typing import Protocol

from fastapi import WebSocket

from telemetry_gateway.models import DeviceState

MAX_QUEUE_SIZE = 100 ##buffer limit for message queue for each client to event stay fast and not block the publisher when a client is slow by dropping the slow client 
class StatePublisher(Protocol):
    async def publish(self, state: DeviceState) -> None: ...

## creating a class to manage the connected clients and their message queues, and to handle publishing device state changes to all connected clients
class _ClientConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.task: asyncio.Task | None = None
## The RealtimeHub class manages WebSocket connections and publishes device state changes to all connected clients. 
# It maintains a dictionary of connected clients, each represented by a _ClientConnection instance that holds the WebSocket, a message queue, and a task for sending messages. 
# The publish method enqueues messages for all clients, disconnecting any that exceed the queue limit.
class RealtimeHub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, _ClientConnection] = {}
    
    async def _sender_loop(self, conn: _ClientConnection) -> None:
        try:
            while True:
                message = await conn.queue.get()
                await conn.websocket.send_json(message)
        except Exception:
            self.disconnect(conn.websocket) # this calls conn.task.cancel() on itself!
        finally:
            self._clients.pop(conn.websocket, None)
            
            
    async def connect(self, client: WebSocket) -> None:
        await client.accept()
        conn = _ClientConnection(client)
        self._clients[client] = conn
        conn.task = asyncio.create_task(self._sender_loop(conn))

    def disconnect(self, client: WebSocket) -> None:
        conn = self._clients.pop(client, None)
        if conn and conn.task:
            conn.task.cancel()
    
    ##publish() never waits on the actual network send for any client — it always just enqueues the message instantly
    async def publish(self, state: DeviceState) -> None:
        message = {"type": "device.state.changed", "data": state.to_api()}
        for conn in tuple(self._clients.values()):
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                ##buffer limit exceeded, droping the slow client
                self.disconnect(conn.websocket)
                try:
                    await conn.websocket.close(code=1008, reason="slow_client")
                except Exception:
                    pass

    @property
    def size(self) -> int:
        return len(self._clients)
