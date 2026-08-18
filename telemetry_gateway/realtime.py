from __future__ import annotations

import asyncio
from typing import Protocol

from fastapi import WebSocket

from telemetry_gateway.models import DeviceState

MAX_QUEUE_SIZE = 10
class StatePublisher(Protocol):
    async def publish(self, state: DeviceState) -> None: ...

class _ClientConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.task: asyncio.Task | None = None

class RealtimeHub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, _ClientConnection] = {}
    
    async def _sender_loop(self, conn: _ClientConnection) -> None:
        try:
            while True:
                message = await conn.queue.get()
                await conn.websocket.send_json(message)
        except Exception:
            self.disconnect(conn.websocket)
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
