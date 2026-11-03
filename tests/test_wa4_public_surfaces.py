"""Wave A / A4 (diagnostic): no production report dumps in the repository or in the image (J-01).

(S-02 / S-03, the invite code of the report in a header and the brake of failed report lookups, went with the public
report route: N03b-1 removed it, the report is read by staff only.)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── J-01 ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout
    except FileNotFoundError:  # a container without git: the working-tree checks above still hold
        return ""


def _ignore_lines(name):
    path = ROOT / name
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()


def test_j01_report_dumps_are_neither_in_git_nor_in_the_image():
    assert "backups/" in _ignore_lines(".gitignore")
    assert "backups/" in _ignore_lines(".dockerignore")
    assert not (ROOT / "backups").exists() or not any((ROOT / "backups").rglob("*.json"))
    tracked = _git("ls-files", "backups")
    if _git("rev-parse", "--is-inside-work-tree").strip() == "true":
        assert tracked.strip() == ""
