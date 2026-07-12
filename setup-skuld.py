#!/usr/bin/env python3
"""SKULD CLI Installer — fuehrt direkt skuld setup aus."""
import subprocess
import sys
import os

# Ins skuld-cli Verzeichnis wechseln
script_dir = os.path.dirname(os.path.abspath(__file__))
cli_dir = os.path.join(script_dir, "ops", "skuld-cli")

print("Installiere Abhaengigkeiten...")
subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
    "click", "rich", "pyyaml", "requests"], check=True)

print("Starte Setup-Wizard...\n")
sys.path.insert(0, cli_dir)
from skuld_cli.cli import main
main(standalone_mode=True)
