"""Eonix Phone Bridge — REST endpoints for mobile pairing.

Registers /phone/* endpoints on the FastAPI app.
Provides QR code pairing, system status, notifications,
and AI command forwarding for the future Eonix mobile app.
"""
from __future__ import annotations

import base64
import io
import json
import os
import secrets
import socket
from datetime import datetime

import psutil
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/phone", tags=["phone"])


def _gen_token() -> str:
    return secrets.token_hex(16)


@router.get("/pair")
async def phone_pair():
    """Returns a QR code PNG (base64) that the phone app scans to connect."""
    ip = socket.gethostbyname(socket.gethostname())
    port = 7750
    token = _gen_token()
    pair_data = json.dumps({
        "host": ip, "port": port, "token": token,
        "os": "eonix", "ver": "1.5.0",
    })

    # Try qrcode library, fall back to text-only
    try:
        import qrcode
        img = qrcode.make(pair_data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError:
        b64 = base64.b64encode(pair_data.encode()).decode("utf-8")

    return JSONResponse({
        "qr_png_b64": b64,
        "host": ip,
        "port": port,
        "token": token,
        "instructions": "Scan this QR with the Eonix app to pair",
    })


@router.get("/status")
async def phone_status():
    """System status for the phone dashboard."""
    return JSONResponse({
        "os": "Eonix OS",
        "version": "v1.5.0-dev",
        "week": 49,
        "uptime": int(psutil.boot_time()),
        "cpu_pct": psutil.cpu_percent(0.1),
        "ram_pct": psutil.virtual_memory().percent,
        "disk_pct": psutil.disk_usage("/").percent,
        "time": datetime.now().isoformat(),
    })


@router.post("/notify")
async def phone_notify(body: dict):
    """Send a desktop notification from the phone."""
    title = body.get("title", "Eonix Phone")
    msg = body.get("body", "Notification")
    try:
        os.system(f'notify-send "{title}" "{msg}"')
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/command")
async def phone_command(body: dict):
    """Execute an AI command from phone (delegates to /api/ai/command)."""
    text = (body.get("text") or "").lower().strip()
    # Basic responses — full delegation in Week 50
    if "cpu" in text:
        return JSONResponse({
            "response": f"CPU: {psutil.cpu_percent(0.5)}%",
            "action": "info"})
    if "ram" in text:
        m = psutil.virtual_memory()
        return JSONResponse({
            "response": f"RAM: {m.percent}% used",
            "action": "info"})
    return JSONResponse({
        "response": f"Command '{text}' received from phone.",
        "action": "queued"})
