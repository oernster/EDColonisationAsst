#!/usr/bin/env python3
"""Build EDColonisationAsstInstaller.exe (single-file per-user installer).

Workflow (from the project root):

1) Build the runtime:    python buildexe.py
2) Build the installer:  python buildinstaller.py

This script:
- Ensures the frontend production bundle exists (npm run build).
- Stages a curated payload under build/payload/ (backend sources, the
  built frontend, icons, LICENSE, VERSION and the runtime EXE from
  dist-runtime/).
- Compiles the PySide6 installer UI (installer/app.py) into a single
  onefile EXE with the payload embedded.

Outputs:
- dist-installer/EDColonisationAsstInstaller.exe

Nuitka intermediates are kept under build/ (gitignored).
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
RUNTIME_EXE_NAME = "EDColonisationAsst"
INSTALLER_NAME = "EDColonisationAsstInstaller"

INSTALLER_ENTRY = PROJECT_ROOT / "installer" / "app.py"
ICON_FILE = PROJECT_ROOT / "EDColonisationAsst.ico"
VERSION_FILE = PROJECT_ROOT / "VERSION"
BUILD_ID_FILE = PROJECT_ROOT / "BUILD_ID"
LICENSE_FILE = PROJECT_ROOT / "LICENSE"

BUILD_DIR = PROJECT_ROOT / "build"
PAYLOAD_DIR = BUILD_DIR / "payload"
RUNTIME_DIST_DIR = PROJECT_ROOT / "dist-runtime"
RUNTIME_EXE = RUNTIME_DIST_DIR / f"{RUNTIME_EXE_NAME}.exe"
DIST_DIR = PROJECT_ROOT / "dist-installer"

VERSION_FALLBACK = "0.0.0"
PE_VERSION_PARTS = 4
UNLINK_RETRY_ATTEMPTS = 20
UNLINK_RETRY_DELAY_S = 0.15
BYTES_PER_MB = 1024 * 1024

# Loose project-root files staged into the payload, if present.
PAYLOAD_FILES = (
    "EDColonisationAsst.ico",
    "EDColonisationAsst.png",
    "LICENSE",
    "VERSION",
)

# Project directories staged into the payload, if present.
PAYLOAD_DIRS = (
    "backend",
    "frontend",
)

# Directories excluded from the payload (dev, VC and coverage artefacts).
PAYLOAD_IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".benchmarks",
    "htmlcov",
    ".pytest_cache",
    "__pycache__",
    "tests",
    "node_modules",
}

# Files excluded from the payload.
PAYLOAD_IGNORE_FILES = {
    ".coverage",
    ".git",
    ".gitignore",
    "guiinstaller.log",
    ".env",
    "commander.yaml",
    "pytest.ini",
    "requirements-dev.txt",
}


def read_version() -> str:
    """Read the canonical version from the top-level VERSION file."""
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        return raw or VERSION_FALLBACK
    except OSError:
        return VERSION_FALLBACK


def pe_version(version: str) -> str:
    """Convert a version string into a 4-part numeric PE version."""
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


def _ensure_frontend_dist_built() -> None:
    """Ensure frontend/dist exists, running `npm run build` when npm exists.

    Node.js/npm are developer-machine dependencies only; end users never
    need them. Without npm on PATH an existing frontend/dist is accepted;
    a missing one is a hard error.
    """
    frontend_dir = PROJECT_ROOT / "frontend"
    if not frontend_dir.exists():
        print("[buildinstaller] frontend/ not found; skipping frontend build.")
        return

    dist_dir = frontend_dir / "dist"
    npm_exe = shutil.which("npm")
    if not npm_exe:
        if dist_dir.exists() and any(dist_dir.iterdir()):
            print(
                "[buildinstaller] WARNING: npm not found on PATH; using the "
                f"existing frontend build at: {dist_dir}"
            )
            return
        raise RuntimeError(
            "npm was not found on PATH and frontend/dist is missing. "
            "Install Node.js/npm, or build the frontend on a machine that "
            "has npm first."
        )

    print("[buildinstaller] Running `npm run build` for the frontend...")
    result = subprocess.run(
        [npm_exe, "--prefix", str(frontend_dir), "run", "build"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "`npm run build` failed. Inspect the npm output, fix any "
            "errors and re-run buildinstaller.py."
        )
    if not dist_dir.exists() or not any(dist_dir.iterdir()):
        raise RuntimeError(
            "`npm run build` completed but frontend/dist is missing or empty."
        )
    print(f"[buildinstaller] Frontend production build ready at: {dist_dir}")


def _ignore_unwanted(dirpath: str, names: list[str]) -> set[str]:
    """copytree ignore callback excluding dev, VC and coverage artefacts."""
    return {
        name
        for name in names
        if name in PAYLOAD_IGNORE_DIRS or name in PAYLOAD_IGNORE_FILES
    }


def _ensure_payload_dir() -> Path:
    """Stage a fresh curated payload under build/payload/.

    The payload is always rebuilt from curated sources so version bumps and
    code changes are never shipped stale.
    """
    if PAYLOAD_DIR.exists():
        shutil.rmtree(PAYLOAD_DIR)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for name in PAYLOAD_FILES:
        src = PROJECT_ROOT / name
        if src.exists():
            shutil.copy2(src, PAYLOAD_DIR / name)
            print(f"[buildinstaller] Payload file: {src}")

    # The runtime EXE comes from dist-runtime/ (built by buildexe.py) and is
    # staged under its plain name so the installed layout is unchanged.
    shutil.copy2(RUNTIME_EXE, PAYLOAD_DIR / f"{RUNTIME_EXE_NAME}.exe")
    print(f"[buildinstaller] Payload runtime: {RUNTIME_EXE}")

    for name in PAYLOAD_DIRS:
        src = PROJECT_ROOT / name
        if not src.exists():
            continue
        dst = PAYLOAD_DIR / name
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_unwanted)
        print(f"[buildinstaller] Payload dir:  {src}")

        # Ensure the built frontend assets are always present even if an
        # ignore rule or tooling quirk skipped them.
        if name == "frontend":
            dist_src = src / "dist"
            dist_dst = dst / "dist"
            if dist_src.exists():
                shutil.copytree(dist_src, dist_dst, dirs_exist_ok=True)
                print(f"[buildinstaller] Payload frontend build: {dist_src}")
            else:
                print(
                    "[buildinstaller] WARNING: frontend/dist not found while "
                    "copying payload; /app/ will not serve the web UI."
                )

    # The tray controller must ship so installed shortcuts can start the app.
    tray_payload = PAYLOAD_DIR / "backend" / "src" / "tray_app.py"
    if not tray_payload.exists():
        raise RuntimeError(
            f"tray_app.py is missing from the payload ('{tray_payload}'). "
            "Ensure backend/src/tray_app.py exists and is not excluded by "
            "ignore rules."
        )

    # Work around Nuitka stripping *.py files from data directories: ship
    # backend sources as *.py_ and let the installer rename them back on
    # deployment (see installer/app.py).
    backend_src_payload = PAYLOAD_DIR / "backend" / "src"
    if backend_src_payload.exists():
        renamed_count = 0
        for py_file in backend_src_payload.rglob("*.py"):
            py_file.rename(py_file.with_suffix(".py_"))
            renamed_count += 1
        print(
            f"[buildinstaller] Renamed {renamed_count} backend sources to "
            "*.py_ for payload shipping"
        )

    if not any(PAYLOAD_DIR.iterdir()):
        raise RuntimeError(f"Staged payload directory '{PAYLOAD_DIR}' is empty.")

    print(f"[buildinstaller] Payload staged at: {PAYLOAD_DIR}")
    return PAYLOAD_DIR


def _ensure_version_file() -> None:
    """Ensure a VERSION file exists in the project root."""
    if VERSION_FILE.exists():
        print(f"[buildinstaller] Using VERSION: {read_version()}")
        return
    VERSION_FILE.write_text(VERSION_FALLBACK + "\n", encoding="utf-8")
    print(
        f"[buildinstaller] VERSION file not found; created default "
        f"{VERSION_FALLBACK}. Update it to match your release version."
    )


def _ensure_build_id_file() -> None:
    """Ensure a BUILD_ID file exists (buildexe.py normally writes it)."""
    if BUILD_ID_FILE.exists():
        return
    BUILD_ID_FILE.write_text("dev\n", encoding="utf-8")
    print(
        "[buildinstaller] BUILD_ID not found; created default 'dev'. "
        "Re-run buildexe.py for a timestamped build id."
    )


def build_installer() -> None:
    """Build the GUI installer executable using Nuitka."""
    if not INSTALLER_ENTRY.exists():
        raise FileNotFoundError(
            f"Could not find the installer UI at: {INSTALLER_ENTRY}"
        )
    if not ICON_FILE.exists():
        raise FileNotFoundError(f"Could not find application icon at: {ICON_FILE}")
    if not RUNTIME_EXE.exists():
        raise FileNotFoundError(
            f"Could not find the runtime EXE at: {RUNTIME_EXE}\n"
            "Run `python buildexe.py` first to build the runtime."
        )

    version = read_version()
    pe_ver = pe_version(version)

    print(f"[buildinstaller] Building installer for {APP_DISPLAY_NAME} v{version}")

    _ensure_frontend_dist_built()
    _ensure_version_file()
    _ensure_build_id_file()
    _ensure_payload_dir()

    cpu_count = os.cpu_count() or 1

    nuitka_args: List[str] = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        f"--jobs={cpu_count}",
        "--windows-console-mode=disable",
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={INSTALLER_NAME}.exe",
        f"--windows-icon-from-ico={ICON_FILE}",
        f"--company-name={APP_AUTHOR}",
        f"--product-name={APP_DISPLAY_NAME} Setup",
        f"--file-version={pe_ver}",
        f"--product-version={pe_ver}",
        f"--file-description={APP_DESCRIPTION} installer",
        f"--copyright=Copyright {APP_AUTHOR}",
        f"--include-data-dir={PAYLOAD_DIR}=payload",
        # The runtime EXE is also embedded as a dedicated data file so it is
        # always present even if Nuitka strips executables from the payload
        # data directory.
        f"--include-data-file={RUNTIME_EXE}=runtime/{RUNTIME_EXE_NAME}.exe",
    ]

    if LICENSE_FILE.exists():
        nuitka_args.append(f"--include-data-file={LICENSE_FILE}=LICENSE")
    if VERSION_FILE.exists():
        nuitka_args.append(f"--include-data-file={VERSION_FILE}=VERSION")
    if BUILD_ID_FILE.exists():
        nuitka_args.append(f"--include-data-file={BUILD_ID_FILE}=BUILD_ID")

    nuitka_args.append(str(INSTALLER_ENTRY))

    print("[buildinstaller] Running Nuitka with args:")
    for part in nuitka_args:
        print("  ", part)

    result = subprocess.run(nuitka_args, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Nuitka build failed with exit code {result.returncode}")

    built_exe = BUILD_DIR / f"{INSTALLER_NAME}.exe"
    if not built_exe.exists():
        raise RuntimeError(
            f"Build finished but {built_exe} was not found. "
            "Check the Nuitka output for details."
        )

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    final_exe = DIST_DIR / f"{INSTALLER_NAME}.exe"
    retry_unlink(final_exe)
    shutil.move(str(built_exe), str(final_exe))

    size_mb = final_exe.stat().st_size / BYTES_PER_MB
    print(f"[buildinstaller] Installer build complete: {final_exe} ({size_mb:.1f} MB)")


def main() -> int:
    try:
        build_installer()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[buildinstaller] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
