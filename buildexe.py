#!/usr/bin/env python3
"""Build the self-contained EDCA runtime EXE with Nuitka.

Workflow (from the project root):

1) Build the runtime:    python buildexe.py
2) Build the installer:  python buildinstaller.py

This script packages backend/src/runtime_entry.py into a single
self-contained Windows executable so that end users do not need a
system-wide Python installation.

Behaviour of the built EXE:
- In DEV mode (run via python) it delegates to the launcher window and
  virtual-environment logic, leaving developer workflows unchanged.
- In FROZEN mode (the built EXE) it starts the backend in-process, shows
  the startup splash and provides the Qt tray UI.

Outputs:
- dist-runtime/EDColonisationAsst.exe   (the runtime)
- BUILD_ID                              (refreshed build marker)

Nuitka intermediates are kept under build/ (gitignored). Set
EDCA_DEBUG_CONSOLE=1 to build with an attached console for debugging.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent

APP_DISPLAY_NAME = "Elite: Dangerous Colonisation Assistant"
APP_DESCRIPTION = "Colonisation assistant for Elite: Dangerous"
APP_AUTHOR = "Oliver Ernster"
EXE_NAME = "EDColonisationAsst"

ENTRY_SCRIPT = PROJECT_ROOT / "backend" / "src" / "runtime_entry.py"
ICON_FILE = PROJECT_ROOT / "EDColonisationAsst.ico"
VERSION_FILE = PROJECT_ROOT / "VERSION"
BUILD_ID_FILE = PROJECT_ROOT / "BUILD_ID"

BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist-runtime"

VERSION_FALLBACK = "0.0.0"
PE_VERSION_PARTS = 4
CONSOLE_MODE_RELEASE = "disable"
CONSOLE_MODE_DEBUG = "attach"
DEBUG_CONSOLE_ENV_VAR = "EDCA_DEBUG_CONSOLE"
UNLINK_RETRY_ATTEMPTS = 20
UNLINK_RETRY_DELAY_S = 0.15
BYTES_PER_MB = 1024 * 1024


def read_version() -> str:
    """Read the canonical version from the top-level VERSION file."""
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        return raw or VERSION_FALLBACK
    except OSError:
        return VERSION_FALLBACK


def pe_version(version: str) -> str:
    """Convert a version string into a 4-part numeric PE version.

    Non-digit characters are stripped per dotted segment and the result is
    padded or truncated to exactly PE_VERSION_PARTS parts, so "2.8.1"
    becomes "2.8.1.0" and "1.2.0-rc1" becomes "1.2.0.0".
    """
    parts: List[str] = []
    for segment in version.split("."):
        digits = "".join(ch for ch in segment if ch.isdigit())
        parts.append(digits or "0")
    parts = parts[:PE_VERSION_PARTS]
    while len(parts) < PE_VERSION_PARTS:
        parts.append("0")
    return ".".join(parts)


def retry_unlink(path: Path) -> None:
    """Delete a file that may be briefly locked by AV or Explorer."""
    if not path.exists():
        return
    last_exc: Exception | None = None
    for _ in range(UNLINK_RETRY_ATTEMPTS):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(UNLINK_RETRY_DELAY_S)
    if last_exc is not None:
        raise last_exc


def write_build_id() -> str:
    """Write a build identifier (UTC timestamp + short git SHA) to BUILD_ID."""
    from datetime import datetime, UTC

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sha = "nogit"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            sha = result.stdout.strip()
    except Exception:  # noqa: BLE001
        pass

    build_id = f"{stamp}-{sha}"
    try:
        BUILD_ID_FILE.write_text(build_id + "\n", encoding="utf-8")
    except OSError:
        # Not fatal; the health endpoint just will not show a build id.
        pass
    return build_id


def build_exe() -> None:
    """Build the runtime executable using Nuitka."""
    if not ENTRY_SCRIPT.exists():
        raise FileNotFoundError(
            f"Could not find runtime entry script at: {ENTRY_SCRIPT}"
        )
    if not ICON_FILE.exists():
        raise FileNotFoundError(
            f"Could not find application icon at: {ICON_FILE}\n"
            "Place the .ico file in the project root or update buildexe.py."
        )

    version = read_version()
    pe_ver = pe_version(version)
    build_id = write_build_id()

    print(f"[buildexe] Building {APP_DISPLAY_NAME} v{version}")
    print(f"[buildexe] Entry script: {ENTRY_SCRIPT}")
    print(f"[buildexe] BUILD_ID: {build_id}")

    cpu_count = os.cpu_count() or 1
    debug_console = os.environ.get(DEBUG_CONSOLE_ENV_VAR, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    console_mode = CONSOLE_MODE_DEBUG if debug_console else CONSOLE_MODE_RELEASE
    print(f"[buildexe] Windows console mode: {console_mode}")

    nuitka_args: List[str] = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        f"--jobs={cpu_count}",
        f"--windows-console-mode={console_mode}",
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={EXE_NAME}.exe",
        f"--windows-icon-from-ico={ICON_FILE}",
        f"--company-name={APP_AUTHOR}",
        f"--product-name={APP_DISPLAY_NAME}",
        f"--file-version={pe_ver}",
        f"--product-version={pe_ver}",
        f"--file-description={APP_DESCRIPTION}",
        f"--copyright=Copyright {APP_AUTHOR}",
    ]

    # Ship the build marker and canonical version next to the module inside
    # the bundle so the frozen backend reports them correctly.
    if BUILD_ID_FILE.exists():
        nuitka_args.append(f"--include-data-file={BUILD_ID_FILE}=BUILD_ID")
    if VERSION_FILE.exists():
        nuitka_args.append(f"--include-data-file={VERSION_FILE}=VERSION")

    nuitka_args.append(str(ENTRY_SCRIPT))

    print("[buildexe] Running Nuitka with args:")
    for part in nuitka_args:
        print("  ", part)

    result = subprocess.run(nuitka_args, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Nuitka build failed with exit code {result.returncode}")

    built_exe = BUILD_DIR / f"{EXE_NAME}.exe"
    if not built_exe.exists():
        raise RuntimeError(
            f"Build finished but {built_exe} was not found. "
            "Check the Nuitka output for details."
        )

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    final_exe = DIST_DIR / f"{EXE_NAME}.exe"
    retry_unlink(final_exe)
    shutil.move(str(built_exe), str(final_exe))

    size_mb = final_exe.stat().st_size / BYTES_PER_MB
    print(f"[buildexe] Runtime build complete: {final_exe} ({size_mb:.1f} MB)")


def main() -> int:
    try:
        build_exe()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[buildexe] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
