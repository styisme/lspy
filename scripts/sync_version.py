#!/usr/bin/env python3
"""Keep the project version in sync with CHANGELOG.md (the single source of truth).

Usage:
    python scripts/sync_version.py            # write the version into lspy.py / pyproject.toml
    python scripts/sync_version.py --check    # verify only, exit 1 on mismatch (CI)

The version is taken from the first "## [x.y.z] - ..." heading in CHANGELOG.md.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
MAIN = ROOT / "lspy.py"
PYPROJECT = ROOT / "pyproject.toml"


def read_changelog_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    if not m:
        raise SystemExit("error: no '## [x.y.z]' heading found in CHANGELOG.md")
    return m.group(1)


def current_in_main():
    text = MAIN.read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("error: VERSION not found in lspy.py")
    return m.group(1)


def current_in_pyproject():
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("error: version not found in pyproject.toml")
    return m.group(1)


def replace_version(path, pattern, version):
    text = path.read_text(encoding="utf-8")

    def _sub(m):
        return m.group(1) + version + m.group(3)

    new, count = re.subn(pattern, _sub, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"error: could not rewrite version in {path.name}")
    path.write_text(new, encoding="utf-8", newline="\n")


def main(argv):
    check_only = "--check" in argv
    wanted = read_changelog_version()
    main_ver = current_in_main()
    proj_ver = current_in_pyproject()

    if main_ver == wanted and proj_ver == wanted:
        print(f"version ok: {wanted}")
        return 0

    if check_only:
        print(
            f"error: version mismatch (CHANGELOG={wanted}, lspy.py={main_ver}, pyproject.toml={proj_ver})",
            file=sys.stderr,
        )
        return 1

    replace_version(MAIN, '^(VERSION\\s*=\\s*")(\\d+\\.\\d+\\.\\d+)(")', wanted)
    replace_version(PYPROJECT, '^(version\\s*=\\s*")(\\d+\\.\\d+\\.\\d+)(")', wanted)
    if current_in_main() != wanted or current_in_pyproject() != wanted:
        print("error: version rewrite did not take effect", file=sys.stderr)
        return 1
    print(f"version synced: {main_ver}/{proj_ver} -> {wanted}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
