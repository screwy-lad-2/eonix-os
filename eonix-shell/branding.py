"""Branding utilities for Eonix shell startup visuals."""

from __future__ import annotations

import random

GREEN = "\033[92m"
RESET = "\033[0m"

TAGLINES = [
    "Intent-driven by design",
    "Your AI-native operating core",
    "Fast. Adaptive. Autonomous.",
    "Booting intelligence, not just software",
    "From command line to cognition",
]

BOOT_ART = r"""
███████╗ ██████╗ ███╗   ██╗██╗██╗  ██╗
██╔════╝██╔═══██╗████╗  ██║██║╚██╗██╔╝
█████╗  ██║   ██║██╔██╗ ██║██║ ╚███╔╝
██╔══╝  ██║   ██║██║╚██╗██║██║ ██╔██╗
███████╗╚██████╔╝██║ ╚████║██║██╔╝ ██╗
╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝
""".strip("\n")


def progress_bar(value: float, width: int = 20) -> str:
    """Render a fixed-width progress bar from a 0..1 float value."""
    value = max(0.0, min(1.0, float(value)))
    width = max(1, int(width))
    filled = int(round(value * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def status_line(label, value, unit="", ok=True) -> str:
    """Build a compact status line with semantic health marker."""
    marker = "OK" if ok else "WARN"
    suffix = f" {unit}" if unit else ""
    return f"{marker} | {label}: {value}{suffix}"


def format_banner(goal, progress, ram, model, memories, peers) -> str:
    """Return a startup status banner that includes all key shell fields."""
    bar = progress_bar(float(progress), width=20)
    lines = [
        "EONIX SHELL STARTUP",
        f"Goal: {goal}",
        f"Progress: {bar} {int(round(float(progress) * 100))}%",
        f"RAM: {ram}",
        f"Model: {model}",
        f"Memories: {memories}",
        f"Peers: {peers}",
    ]
    return "\n".join(lines)


def print_boot_art(version, device_id, tagline=None):
    """Print green ASCII boot art with version, device id, and tagline."""
    chosen = tagline if tagline else random.choice(TAGLINES)
    text = "\n".join(
        [
            f"{GREEN}{BOOT_ART}{RESET}",
            f"{GREEN}Version: {version} | Device: {device_id}{RESET}",
            f"{GREEN}{chosen}{RESET}",
        ]
    )
    print(text)
    return text


def test_progress_bar_correct_fill_at_50_percent():
    assert progress_bar(0.5, width=20) == "[##########----------]"


def test_boot_art_contains_version(capsys):
    print_boot_art("v0.6.2", "dev-01", tagline="Test tagline")
    out = capsys.readouterr().out
    assert "v0.6.2" in out


def test_format_banner_contains_all_fields():
    text = format_banner("Ship Week 21", 0.65, "3.2GB free", "v1.2", 120, 3)
    for token in ["Ship Week 21", "65%", "3.2GB free", "v1.2", "120", "3"]:
        assert token in text