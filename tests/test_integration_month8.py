# -*- coding: utf-8 -*-
"""Week 52 integration tests — emoji fix, phone app, updates app, sync engine."""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMOJI_RE = re.compile(
    "["
    "\U00010000-\U0010ffff"
    "\u2600-\u27bf"
    "\u2300-\u23ff"
    "\ufe0e\ufe0f"
    "\u200d"
    "]+", re.UNICODE)


def test_no_emoji_in_wm_titles():
    """Window titles must be ASCII — no emoji garble in VirtualBox."""
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    for line in c.splitlines():
        if "window_manager.open" in line:
            assert not EMOJI_RE.search(line), f"Emoji in title: {line.strip()}"


def test_no_emoji_in_dock_apps():
    """Dock labels must be ASCII."""
    f = os.path.join(REPO, "eonix-desktop/dock.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    for line in c.splitlines():
        if line.strip().startswith('("') and ("EonixShell" in line or "Files" in line):
            assert not EMOJI_RE.search(line), f"Emoji in dock: {line.strip()}"


def test_phone_app_exists():
    f = os.path.join(REPO, "eonix-desktop/apps/phone_app.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "PhoneApp" in c
    assert "dialpad" in c.lower() or "grid" in c.lower()
    assert "_contacts" in c
    assert "CONTACTS_FILE" in c


def test_updates_app_exists():
    f = os.path.join(REPO, "eonix-desktop/apps/updates_app.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "UpdatesApp" in c
    assert "CHANGELOG" in c
    assert "Check Updates" in c


def test_sync_server_exists():
    f = os.path.join(REPO, "eonix-sync/sync_server.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "/sync/push" in c
    assert "/sync/pull" in c
    assert "updated_at" in c
    assert "start_server" in c


def test_sync_client_exists():
    f = os.path.join(REPO, "eonix-sync/sync_client.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "push_table" in c
    assert "pull_table" in c
    assert "full_sync" in c


def test_qr_pair_exists():
    f = os.path.join(REPO, "eonix-sync/qr_pair.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "get_local_ip" in c
    assert "make_qr" in c


def test_cpu_animation_throttled():
    f = os.path.join(REPO, "eonix-desktop/dock.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "timeout_add(16" not in c, "16ms timer still present"
    assert "timeout_add(33" not in c, "33ms timer still present"


def test_fix_emoji_script_exists():
    f = os.path.join(REPO, "eonix-desktop/fix_emoji_vm.sh")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "fc-cache" in c
    assert "Noto" in c


def test_sync_tab_in_settings():
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "_panel_sync" in c
    assert "Sync Now" in c
    assert "Show QR" in c
    assert "localhost:7740" in c


def test_phone_launch_in_desktop():
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "PhoneApp" in c
    assert '"Phone"' in c


def test_updates_launch_in_desktop():
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "UpdatesApp" in c
    assert '"Updates"' in c


def test_start_script_has_emoji_fix():
    f = os.path.join(REPO, "start_eonix.sh")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "fix_emoji_vm.sh" in c
    assert "Noto Color Emoji" in c


def test_start_script_has_sync_server():
    f = os.path.join(REPO, "start_eonix.sh")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "sync_server.py" in c
    assert "7740" in c


def test_qrcode_in_requirements():
    f = os.path.join(REPO, "requirements.txt")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "qrcode" in c


def test_dock_ascii_labels():
    """Dock should use ASCII labels like SH, DIR, AIM, etc."""
    f = os.path.join(REPO, "eonix-desktop/dock.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    for label in ["SH", "DIR", "AIM", "CFG", "HUB", "BOT", "AI", "PAD", "SYS"]:
        assert f'"{label}"' in c, f"Missing dock label: {label}"


def test_settings_has_8_panels():
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    for p in ["appearance", "ai", "display", "voice", "sync", "privacy", "updates", "about"]:
        assert p in c, f"Missing panel: {p}"


def test_sync_server_no_flask():
    """Sync server should use stdlib, not Flask."""
    f = os.path.join(REPO, "eonix-sync/sync_server.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "flask" not in c.lower()
