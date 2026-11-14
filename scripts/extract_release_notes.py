#!/usr/bin/env python3
"""Extract the newest CHANGELOG entry for the GitHub Release body.

Writes two files (used by .github/workflows/release.yml):
    .release_version  - the version string (e.g. 1.19.0)
    .release_notes.md - the body of that CHANGELOG section
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def main():
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(
        r"^##\s*\[(\d+\.\d+\.\d+)\][^\n]*\n(.*?)(?=^##\s*\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise SystemExit("error: no '## [x.y.z]' section found in CHANGELOG.md")

    version = m.group(1)
    notes = m.group(2).strip() + "\n"

    (ROOT / ".release_version").write_text(version + "\n", encoding="utf-8")
    (ROOT / ".release_notes.md").write_text(notes, encoding="utf-8")
    print(f"release notes prepared for {version}")


if __name__ == "__main__":
    main()
