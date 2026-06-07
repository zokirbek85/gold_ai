import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from src.api.deps import get_current_user_ws
from src.storage.redis_store import redis_async

router = APIRouter()


async def _subscribe_and_forward(websocket: WebSocket, channel: str) -> None:
    pubsub = redis_async.pubsub()
    await pubsub.subscribe(channel)
    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    if not isinstance(data, str):
                        data = json.dumps(data)
                    await websocket.send_text(data)
            await asyncio.sleep(0.05)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@router.websocket("/ws/market-data")
async def market_data_ws(websocket: WebSocket, current_user=Depends(get_current_user_ws), symbol: Optional[str] = None):
    await websocket.accept()
    channel = "market-data-updates"
    if symbol:
        channel = f"market-data-updates:{symbol}"
    try:
        await _subscribe_and_forward(websocket, channel)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/indicators")
async def indicators_ws(websocket: WebSocket, current_user=Depends(get_current_user_ws), symbol: Optional[str] = None):
    await websocket.accept()
    channel = "indicator-updates"
    if symbol:
        channel = f"indicator-updates:{symbol}"
    try:
        await _subscribe_and_forward(websocket, channel)
    except WebSocketDisconnect:
        return
