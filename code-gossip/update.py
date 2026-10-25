#!/usr/bin/env python3
"""Installed entry point for Code Gossip updates."""
from pathlib import Path
from updates.cli import main

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parent))
