"""
Eonix OS — Cross-Device Sync Server
=====================================
WebSocket relay server for CRDT-based state sync between
Eonix devices. Supports LAN direct (mDNS) and internet relay.

Usage: python3 sync_server.py
"""

import asyncio
import json
import hashlib
import os
import ssl
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    raise SystemExit(1)


# ---- Device Registry ----

class DeviceRegistry:
    """Track connected Eonix devices."""

    def __init__(self):
        self.devices: dict[str, websockets.WebSocketServerProtocol] = {}
        self.device_states: dict[str, dict] = {}

    def register(self, device_id: str, ws):
        self.devices[device_id] = ws
        print(f"[Sync] Device connected: {device_id}")

    def unregister(self, device_id: str):
        self.devices.pop(device_id, None)
        print(f"[Sync] Device disconnected: {device_id}")

    async def broadcast(self, sender_id: str, message: dict):
        """Send a message to all connected devices except the sender."""
        disconnected = []
        for device_id, ws in self.devices.items():
            if device_id != sender_id:
                try:
                    await ws.send(json.dumps(message))
                except websockets.ConnectionClosed:
                    disconnected.append(device_id)

        for device_id in disconnected:
            self.unregister(device_id)


registry = DeviceRegistry()


# ---- WebSocket Handler ----

async def handle_device(ws):
    """Handle a single device connection."""
    device_id = None

    try:
        # First message must be authentication
        auth_msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
        auth_data = json.loads(auth_msg)

        if auth_data.get("type") != "auth":
            await ws.close(1008, "Expected auth message")
            return

        device_id = auth_data.get("device_id", "unknown")
        registry.register(device_id, ws)

        # Send last known state if device is reconnecting
        if device_id in registry.device_states:
            await ws.send(json.dumps({
                "type": "state_restore",
                "state": registry.device_states[device_id],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        # Main message loop
        async for message in ws:
            data = json.loads(message)
            msg_type = data.get("type", "unknown")

            if msg_type == "crdt_update":
                # CRDT change payload — relay to other devices
                registry.device_states[device_id] = data.get("state", {})
                await registry.broadcast(device_id, {
                    "type": "crdt_update",
                    "from_device": device_id,
                    "payload": data.get("payload"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "context_delta":
                # ContextAgent delta — relay to other devices
                await registry.broadcast(device_id, {
                    "type": "context_delta",
                    "from_device": device_id,
                    "events": data.get("events", []),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "goal_sync":
                # GoalEngine state replication
                await registry.broadcast(device_id, {
                    "type": "goal_sync",
                    "from_device": device_id,
                    "goals": data.get("goals", []),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "ping":
                await ws.send(json.dumps({"type": "pong"}))

    except websockets.ConnectionClosed:
        pass
    except asyncio.TimeoutError:
        await ws.close(1008, "Auth timeout")
    finally:
        if device_id:
            registry.unregister(device_id)


# ---- Server Startup ----

async def main():
    host = os.getenv("EONIX_SYNC_HOST", "0.0.0.0")
    port = int(os.getenv("EONIX_SYNC_PORT", "8765"))

    print("=" * 50)
    print("  EONIX Cross-Device Sync Server")
    print("=" * 50)
    print(f"  Listening on ws://{host}:{port}")
    print("  Press Ctrl+C to stop\n")

    async with websockets.serve(handle_device, host, port):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Sync] Server stopped.")
