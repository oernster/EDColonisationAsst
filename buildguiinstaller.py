#!/usr/bin/env python3
"""
Build script for packaging the ED Colonisation Assistant GUI installer
into a Windows .exe using Nuitka.

This script expects:
- The PySide6-based installer UI to live in `guiinstaller.py`
- The project root to contain:
    - EDColonisationAsst.ico   (application icon)
    - build_payload/           (optional curated payload tree to ship with the installer)
    - LICENSE                  (LGPL-3 text, shown in the About dialog)

It is intended to be run via `uv`, for example:

    uv pip install -r requirements.txt
    uv run python buildguiinstaller.py

The resulting installer executable will be created under `./` (current
directory) with the name `EDColonisationAsstInstaller.exe`.

Nuitka notes:
- We use `--onefile` for a single exe.
- We enable the `pyside6` plugin.
- We use `--jobs=N` where N is the number of logical cores, so that
  C compilation can run in parallel where supported by the toolchain.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List
import subprocess


APP_NAME = "Elite: Dangerous Colonisation Assistant"
INSTALLER_NAME = "EDColonisationAsstInstaller"


def build_installer() -> None:
    """Build the GUI installer executable using Nuitka."""
    project_root = Path(__file__).resolve().parent

    gui_script = project_root / "guiinstaller.py"
    if not gui_script.exists():
        raise FileNotFoundError(
            f"Could not find guiinstaller.py at: {gui_script}\n"
            "Make sure the installer UI script has been renamed to guiinstaller.py."
        )

    icon_path = project_root / "EDColonisationAsst.ico"
    if not icon_path.exists():
        raise FileNotFoundError(
            f"Could not find EDColonisationAsst.ico at: {icon_path}\n"
            "Place the .ico file in the project root or update buildguiinstaller.py."
        )

    # Hard-require the self-contained runtime executable so that all shortcuts
    # created by the installer can point at EDColonisationAsst.exe and never
    # fall back to the Python/Node-based developer scripts.
    runtime_exe = project_root / "EDColonisationAsst.exe"
    if not runtime_exe.exists():
        raise FileNotFoundError(
            f"Could not find runtime EXE at: {runtime_exe}\n"
            "Run `uv run python buildruntime.py` to build EDColonisationAsst.exe "
            "before building the GUI installer."
        )

    license_file = project_root / "LICENSE"

    # Ensure the frontend has a production build (frontend/dist) so that the
    # backend can serve the UI directly from static files. This step requires
    # Node.js/npm on the *developer* machine only and has no impact on end
    # users of the installer.
    _ensure_frontend_dist_built(project_root)

    # Decide what to embed as the payload: create or refresh build_payload/
    # as needed so users don't have to manage it manually.
    payload_src: Path = _ensure_payload_dir(project_root)

    # Ensure a simple VERSION file exists in the project root so the
    # installer can reliably report the correct version at runtime, even
    # when backend sources are not directly visible.
    version_file = _ensure_version_file(project_root)

    # Ensure BUILD_ID exists so the installed runtime can expose a precise build
    # marker via /api/health (used to detect stale installs).
    build_id_file = _ensure_build_id_file(project_root)

    print(f"[buildguiinstaller] Building installer for {APP_NAME}")
    print(f"[buildguiinstaller] GUI script: {gui_script}")
    print(f"[buildguiinstaller] Icon: {icon_path}")
    print(f"[buildguiinstaller] Embedding payload from: {payload_src}")

    if license_file.exists():
        print(f"[buildguiinstaller] LICENSE will be bundled from: {license_file}")
    else:
        print(
            "[buildguiinstaller] LICENSE file not found; About dialog will fall back to URL only."
        )

    if version_file.exists():
        print(f"[buildguiinstaller] VERSION will be bundled from: {version_file}")
    else:
        print(
            "[buildguiinstaller] VERSION file not found; installer will fall back to 0.0.0."
        )

    if build_id_file.exists():
        print(f"[buildguiinstaller] BUILD_ID will be bundled from: {build_id_file}")
    else:
        print(
            "[buildguiinstaller] BUILD_ID file not found; health endpoint build_id will be empty."
        )

    # Determine jobs for Nuitka parallel compilation.
    cpu_count = os.cpu_count() or 1
    jobs = str(cpu_count)
    print(f"[buildguiinstaller] Using {jobs} parallel jobs for Nuitka compilation")

    # Base Nuitka arguments.
    # Notes:
    # - --onefile: single exe.
    # - --standalone is implied by --onefile.
    # - --enable-plugin=pyside6: ensures Qt/PySide6 integration.
    # - --jobs: parallel compilation.
    nuitka_args: List[str] = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--enable-plugin=pyside6",
        f"--jobs={jobs}",
        "--windows-console-mode=disable",
        f"--output-filename={INSTALLER_NAME}.exe",
        f"--windows-icon-from-ico={icon_path}",
    ]

    # Data: payload directory as "payload/" inside the bundle.
    if payload_src.exists():
        nuitka_args.append(f"--include-data-dir={payload_src}=payload")

    # Data: runtime EXE as a dedicated data file inside the bundle.
    # This ensures EDColonisationAsst.exe is always present at
    # "runtime/EDColonisationAsst.exe" at installer runtime, even if Nuitka
    # decides to strip or ignore executables inside an included data directory.
    nuitka_args.append(
        f"--include-data-file={runtime_exe}=runtime/EDColonisationAsst.exe"
    )

    # Data: LICENSE file.
    if license_file.exists():
        nuitka_args.append(f"--include-data-file={license_file}=LICENSE")

    # Data: VERSION file for reliable version reporting in the installer.
    if version_file.exists():
        nuitka_args.append(f"--include-data-file={version_file}=VERSION")

    # Data: BUILD_ID file for build provenance.
    if build_id_file.exists():
        nuitka_args.append(f"--include-data-file={build_id_file}=BUILD_ID")

    # Finally, the script to compile.
    nuitka_args.append(str(gui_script))

    print(f"[buildguiinstaller] Running Nuitka with args:")
    for part in nuitka_args:
        print("  ", part)

    result = subprocess.run(nuitka_args)
    if result.returncode != 0:
        raise RuntimeError(f"Nuitka build failed with exit code {result.returncode}")

    dist_path = project_root / f"{INSTALLER_NAME}.exe"
    if dist_path.exists():
        print(f"[buildguiinstaller] Build complete: {dist_path}")
    else:
        print(
            "[buildguiinstaller] Build finished, but "
            f"{INSTALLER_NAME}.exe not found in project root. "
            "Check Nuitka output for details."
        )


def _ensure_frontend_dist_built(project_root: Path) -> None:
    """
    Ensure that frontend/dist exists by running `npm run build` if needed.

    This is a developer-only dependency: Node.js/npm must be available on
    the machine building the installer, but are not required on end-user
    systems. If the build fails, we raise a clear error so the developer
    can fix their Node/npm setup before shipping an incomplete installer.
    """
    frontend_dir = project_root / "frontend"
    if not frontend_dir.exists():
        print(
            "[buildguiinstaller] frontend/ directory not found; skipping frontend build."
        )
        return

    dist_dir = frontend_dir / "dist"
    try:
        if dist_dir.exists() and any(dist_dir.iterdir()):
            print(f"[buildguiinstaller] Using existing frontend build at: {dist_dir}")
            return
    except OSError as exc:
        raise RuntimeError(
            f"[buildguiinstaller] Unable to inspect frontend/dist: {exc}"
        ) from exc

    print(
        "[buildguiinstaller] frontend/dist not found or empty; running `npm run build`..."
    )
    try:
        result = subprocess.run(
            ["npm", "--prefix", str(frontend_dir), "run", "build"],
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            "[buildguiinstaller] Failed to start npm to build the frontend. "
            "Ensure Node.js and npm are installed and available on PATH.\n"
            f"Underlying error: {exc}"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            "[buildguiinstaller] `npm run build` for the frontend failed. "
            "Please inspect the npm output, fix any errors, and re-run "
            "buildguiinstaller.py."
        )

    try:
        if not dist_dir.exists() or not any(dist_dir.iterdir()):
            raise RuntimeError(
                "[buildguiinstaller] `npm run build` completed but frontend/dist "
                "is still missing or empty."
            )
    except OSError as exc:
        raise RuntimeError(
            f"[buildguiinstaller] Unable to inspect frontend/dist after build: {exc}"
        ) from exc

    print(f"[buildguiinstaller] Frontend production build ready at: {dist_dir}")


def _ensure_payload_dir(project_root: Path) -> Path:
    """
    Ensure build_payload/ exists and contains a curated copy of the files
    we want the installer to deploy.

    This avoids accidentally bundling the entire repo (.git, .venv, etc.)
    and gives users a sensible default without manual setup.

    IMPORTANT: The payload directory is always rebuilt fresh so that changes
    to the backend/frontend (including version bumps) are reflected in the
    installer. This prevents stale copies of backend/src/__init__.py from
    causing the installer to report an out-of-date version.
    """
    payload_dir = project_root / "build_payload"

    # Always rebuild the payload directory from curated sources to avoid
    # shipping stale content from a previous build.
    if payload_dir.exists():
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True, exist_ok=True)

    # Curated top-level files to include, if present.
    # Keep this list minimal to avoid bloating the installer with dev docs.
    # NOTE: EDColonisationAsst.exe is the Nuitka-built runtime that embeds
    # Python and all backend dependencies so that end users do not need a
    # system-wide Python installation.
    # VERSION is the single source of truth for the application version and is
    # used by both the backend (__version__) and the installer UI. Including it
    # here ensures that the installed runtime directory always contains a
    # VERSION file next to EDColonisationAsst.exe, so the packaged backend can
    # report the correct version instead of falling back to "0.0.0".
    curated_files = [
        "EDColonisationAsst.ico",
        "EDColonisationAsst.png",
        "LICENSE",
        "VERSION",
        "EDColonisationAsst.exe",
    ]

    # Curated directories to include, if present.
    curated_dirs = [
        "backend",
        "frontend",
    ]

    # Ignore patterns for files/dirs we explicitly do NOT want in the payload.
    # This removes dev/VC/coverage artefacts and anything we don't need at runtime.
    ignore_dir_names = {
        ".git",
        ".venv",
        ".benchmarks",
        "htmlcov",
        ".pytest_cache",
        "__pycache__",
        "tests",
        "node_modules",
    }
    ignore_file_names = {
        ".coverage",
        ".git",
        ".gitignore",
        "guiinstaller.log",
        ".env",
        "commander.yaml",
        "pytest.ini",
        "requirements-dev.txt",
    }

    def _ignore_unwanted(dirpath: str, names: list[str]) -> set[str]:
        """Ignore callback for shutil.copytree to exclude dev/VC/coverage artefacts."""
        ignored: set[str] = set()
        for name in names:
            # Exclude known junk/VC/coverage artefacts entirely.
            if name in ignore_dir_names or name in ignore_file_names:
                ignored.add(name)
        return ignored

    for name in curated_files:
        src = project_root / name
        if src.exists():
            dst = payload_dir / name
            shutil.copy2(src, dst)
            print(f"[buildguiinstaller] Payload file: {src} -> {dst}")

    for name in curated_dirs:
        src = project_root / name
        if src.exists():
            dst = payload_dir / name
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_unwanted)
            print(f"[buildguiinstaller] Payload dir:  {src} -> {dst}")

            # Special case: ensure the built frontend assets (frontend/dist)
            # are always present in the payload, even if they were skipped by
            # ignore rules or tooling quirks.
            if name == "frontend":
                dist_src = src / "dist"
                dist_dst = dst / "dist"
                if dist_src.exists():
                    try:
                        shutil.copytree(dist_src, dist_dst, dirs_exist_ok=True)
                        print(
                            "[buildguiinstaller] Payload frontend build: "
                            f"{dist_src} -> {dist_dst}"
                        )
                    except OSError as exc:
                        raise RuntimeError(
                            "[buildguiinstaller] Failed to copy frontend/dist "
                            f"into payload: {exc}"
                        ) from exc
                else:
                    print(
                        "[buildguiinstaller] WARNING: frontend/dist not found "
                        "while copying payload; /app/ will not serve the web UI."
                    )

    # Hard requirement: the tray controller must be present in the payload so
    # that installed shortcuts can start the app and show the tray icon.
    tray_payload = payload_dir / "backend" / "src" / "tray_app.py"
    if not tray_payload.exists():
        raise RuntimeError(
            "[buildguiinstaller] tray_app.py is missing from the payload "
            f"('{tray_payload}'). The installer would produce shortcuts that "
            "cannot start the tray application. Ensure backend/src/tray_app.py "
            "exists and is not excluded by ignore rules."
        )
    else:
        print(
            f"[buildguiinstaller] Verified tray controller present at: {tray_payload}"
        )

    # Work around Nuitka/packaging behaviour that can strip *.py files from
    # data directories. To ensure the backend sources are shipped as plain
    # files in the payload, we rename them to \"*.py_\" here and let the
    # runtime installer rename them back to \"*.py\" when copying to the
    # final install location.
    backend_src_payload = payload_dir / "backend" / "src"
    if backend_src_payload.exists():
        for py_file in backend_src_payload.rglob("*.py"):
            renamed = py_file.with_suffix(".py_")
            try:
                py_file.rename(renamed)
                print(
                    "[buildguiinstaller] Payload backend source:",
                    f"{py_file} -> {renamed}",
                )
            except OSError as exc:
                raise RuntimeError(
                    "[buildguiinstaller] Failed to rename backend source file "
                    f"for payload shipping: {py_file} -> {renamed}: {exc}"
                ) from exc

    try:
        has_entries = any(payload_dir.iterdir())
    except OSError as exc:
        raise RuntimeError(
            f"Unable to inspect bootstrapped payload directory '{payload_dir}': {exc}"
        ) from exc

    if not has_entries:
        raise RuntimeError(
            f"Bootstrapped payload directory '{payload_dir}' is empty.\n"
            "No curated files or directories were found to copy. "
            "Add at least one of: backend/, frontend/, EDColonisationAsst.exe, etc."
        )

    print(f"[buildguiinstaller] Bootstrapped payload directory at: {payload_dir}")
    return payload_dir


def _read_version_from_version_file(project_root: Path) -> str:
    """
    Read the canonical version from the top-level VERSION file.

    This makes VERSION the single source of truth that is shared by:
    - the backend (__version__ in backend/src/__init__.py)
    - the installer (for About dialogs / metadata)
    - any external tooling that wants to know the app version.
    """
    version_file = project_root / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        return "0.0.0"


def _ensure_version_file(project_root: Path) -> Path:
    """
    Ensure a VERSION file exists in the project root.

    If it already exists, we leave its contents unchanged and log the value.
    If it does not exist, we create it with a safe default ("0.0.0") and
    instruct the developer to update it before shipping.
    """
    version_file = project_root / "VERSION"

    if not version_file.exists():
        try:
            version_file.write_text("0.0.0\n", encoding="utf-8")
            print(
                "[buildguiinstaller] VERSION file not found; created default 0.0.0. "
                "Update this file to match your release version."
            )
        except OSError as exc:
            print(f"[buildguiinstaller] WARNING: Failed to create VERSION file: {exc}")
    else:
        try:
            version = version_file.read_text(encoding="utf-8").strip()
            print(
                f"[buildguiinstaller] Using existing VERSION file with version: {version}"
            )
        except OSError as exc:
            print(
                "[buildguiinstaller] WARNING: Failed to read VERSION file: "
                f"{exc}. Installer will fall back to 0.0.0."
            )

    return version_file


def _ensure_build_id_file(project_root: Path) -> Path:
    """Ensure a BUILD_ID file exists in the project root.

    The runtime build step usually writes BUILD_ID, but the installer can be
    built independently, so we keep this defensive.
    """
    build_id_file = project_root / "BUILD_ID"
    if not build_id_file.exists():
        try:
            build_id_file.write_text("dev\n", encoding="utf-8")
            print(
                "[buildguiinstaller] BUILD_ID file not found; created default 'dev'. "
                "Re-run buildruntime.py for a timestamped build id."
            )
        except OSError as exc:
            print(f"[buildguiinstaller] WARNING: Failed to create BUILD_ID file: {exc}")
    return build_id_file


def main() -> int:
    try:
        build_installer()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[buildguiinstaller] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
