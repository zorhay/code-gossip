#!/usr/bin/env python3
"""Installed entry point for Code Gossip updates."""
from paths import ROOT
from updates.cli import main

if __name__ == "__main__":
    raise SystemExit(main(ROOT))
