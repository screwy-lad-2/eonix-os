# -*- coding: utf-8 -*-
"""QR code device pairing — generates a QR with the sync server URL."""
import socket
import os


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def make_qr(save_path="/tmp/eonix_sync_qr.png"):
    try:
        import qrcode
        ip = get_local_ip()
        url = f"http://{ip}:7740"
        img = qrcode.make(url)
        img.save(save_path)
        return save_path, url
    except ImportError:
        return None, "qrcode not installed"
