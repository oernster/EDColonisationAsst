"""Stage the EDCA runtime as an unfrozen deployment and archive it.

This replaces the Nuitka build. EDCA now ships the way it runs: a plain
interpreter, the runtime dependencies as they come from their wheels and the
application as readable Python. Nothing is compiled.

The reason is measured rather than theoretical. Malwarebytes' heuristic
quarantined the Nuitka-compiled program on sight, wherever it sat, under
Malware.AI.1329201734; the identical application shipped unfrozen scanned clean
across 6,399 files. An application that a security product deletes cannot be
given to anybody; a workaround that asks every user to add an exclusion is not a
product.

Produces:

- build/runtime/                the staged deployment tree
- dist-runtime/edca-runtime.zip the same tree as one archive, which is what the
                                setup program embeds and extracts

Nuitka strips loose executables and .py files out of an included data
directory, so the tree travels as an archive rather than as files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

APP_SHORT_NAME = "EDColonisationAsst"
LAUNCH_SCRIPT_NAME = "edca_launch.py"
RUNTIME_ARCHIVE_NAME = "edca-runtime.zip"

BUILD_DIR = PROJECT_ROOT / "build"
RUNTIME_DIR = BUILD_DIR / "runtime"
DIST_DIR = PROJECT_ROOT / "dist-runtime"
REQUIREMENTS_FILE = PROJECT_ROOT / "backend" / "requirements.txt"
VERSION_FILE = PROJECT_ROOT / "VERSION"
BUILD_ID_FILE = PROJECT_ROOT / "BUILD_ID"
LICENSE_FILE = PROJECT_ROOT / "LICENSE"

VERSION_FALLBACK = "0.0.0-dev"
BYTES_PER_MB = 1024 * 1024

# Parts of the interpreter an installed EDCA never uses. The test suite and the
# Tk stack are the bulk of them; shipping a compiler's worth of test data to
# every commander helps nobody.
INTERPRETER_SKIP_DIRS = (
    "test",
    "tests",
    "idlelib",
    "tkinter",
    "turtledemo",
    "Doc",
    "site-packages",
    "__pycache__",
)
INTERPRETER_SKIP_TOP = ("tcl", "Tools")

# Build-only requirements. Nuitka compiled the old runtime and is imported by
# nothing at run time.
BUILD_ONLY_REQUIREMENTS = ("nuitka",)

# Qt modules EDCA does not use. The tray, the splash and three dialogs need
# Core, Gui and Widgets; everything else is weight a commander downloads once
# and never runs.
QT_SKIP_PREFIXES = (
    "Qt6WebEngine",
    "Qt6WebView",
    "Qt6Quick",
    "Qt6Qml",
    "Qt63D",
    "Qt6Charts",
    "Qt6DataVisualization",
    "Qt6Multimedia",
    "Qt6Designer",
    "Qt6Pdf",
    "Qt6Bluetooth",
    "Qt6Nfc",
    "Qt6SerialPort",
    "Qt6Sql",
    "Qt6Test",
    "Qt6Help",
    "Qt6Location",
    "Qt6Positioning",
    "Qt6Sensors",
    "Qt6RemoteObjects",
    "Qt6Scxml",
    "Qt6SpatialAudio",
    "Qt6TextToSpeech",
)
QT_SKIP_DIRS = (
    "examples",
    "glue",
    "include",
    "typesystems",
    "translations",
    "qml",
    "resources",
    "scripts",
    "support",
    "assistant",
    "designer",
    "linguist",
    "lupdate",
    "lrelease",
)

APP_SOURCE_DIRS = (
    ("backend/src", "backend/src"),
    ("frontend/dist", "frontend/dist"),
)
APP_FILES = (
    "VERSION",
    "BUILD_ID",
    "LICENSE",
    f"{APP_SHORT_NAME}.ico",
    f"{APP_SHORT_NAME}.png",
    LAUNCH_SCRIPT_NAME,
)


def read_version() -> str:
    """Return the canonical version; the development sentinel when absent."""
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return VERSION_FALLBACK
    return text or VERSION_FALLBACK


def write_build_id() -> str:
    """Write a build identifier (UTC timestamp plus short git SHA)."""
    from datetime import UTC, datetime

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sha = "nogit"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            sha = result.stdout.strip()
    except OSError:
        pass

    build_id = f"{stamp}-{sha}"
    try:
        BUILD_ID_FILE.write_text(build_id + "\n", encoding="utf-8")
    except OSError:
        pass
    return build_id


def _interpreter_source() -> Path:
    """Return the interpreter installation this build copies from."""
    base = Path(sys.base_prefix)
    if not (base / "python.exe").is_file():
        raise RuntimeError(
            f"No python.exe under {base}. Run this from a virtual environment "
            "whose base interpreter is a normal Windows installation."
        )
    return base


def _copy_interpreter(target: Path) -> None:
    """Copy the interpreter, leaving out what an installed EDCA never runs."""
    source = _interpreter_source()
    print(f"[buildruntime] Interpreter: {source}")

    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped = {name for name in names if name in INTERPRETER_SKIP_DIRS}
        if Path(directory) == source:
            skipped |= {name for name in names if name in INTERPRETER_SKIP_TOP}
        return skipped

    shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)


def _runtime_requirements() -> list[str]:
    """Return the requirement lines an installed EDCA actually needs."""
    lines = REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
    wanted: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split("=")[0].split(">")[0].split("<")[0].split("[")[0]
        if name.strip().lower() in BUILD_ONLY_REQUIREMENTS:
            continue
        wanted.append(stripped)
    return wanted


def _install_dependencies(target: Path) -> None:
    """Install the runtime dependencies into the staged tree."""
    requirements = _runtime_requirements()
    print(f"[buildruntime] Installing {len(requirements)} requirement(s)")
    site_packages = target / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    # --no-warn-conflicts because a --target install is not an environment
    # install: pip still checks what it writes against the packages of the
    # interpreter it happens to be running from, so unrelated tools installed
    # there are reported as conflicting with pins that never went near them.
    # The report is alarming, names projects with nothing to do with EDCA and
    # says nothing about whether the staged tree is correct. pip's exit code,
    # checked below, is what actually settles that.
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-conflicts",
        "--no-compile",
        "--target",
        str(site_packages),
        *requirements,
    ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"pip install failed with exit code {result.returncode}. The staged "
            "runtime is incomplete."
        )


def _prune_qt(target: Path) -> int:
    """Remove the Qt modules EDCA does not use. Returns megabytes saved."""
    pyside = target / "Lib" / "site-packages" / "PySide6"
    if not pyside.is_dir():
        return 0

    removed = 0
    for path in list(pyside.iterdir()):
        if path.is_dir() and path.name in QT_SKIP_DIRS:
            removed += _directory_bytes(path)
            shutil.rmtree(path, ignore_errors=True)
            continue
        if path.is_file() and path.name.startswith(QT_SKIP_PREFIXES):
            removed += path.stat().st_size
            path.unlink(missing_ok=True)
            continue
        # The Python bindings for a module that has gone are dead weight too.
        if path.is_file() and path.suffix == ".pyd":
            module = "Qt6" + path.stem.removeprefix("Qt")
            if module.startswith(QT_SKIP_PREFIXES):
                removed += path.stat().st_size
                path.unlink(missing_ok=True)
    return removed // BYTES_PER_MB


def _directory_bytes(path: Path) -> int:
    """Return the total size of a directory tree."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _name_the_executable(target: Path) -> Path:
    """Give the windowed interpreter the application's own name.

    The file is a copy of the signed pythonw.exe. Renaming does not disturb its
    signature, which covers the contents rather than the filename. It is also
    what puts the application's own name in the task list, on the taskbar
    button and in the shortcut, exactly as the compiled build did.
    """
    source = target / "pythonw.exe"
    if not source.is_file():
        raise RuntimeError(f"No pythonw.exe in the staged tree at {target}.")
    destination = target / f"{APP_SHORT_NAME}.exe"
    shutil.copy2(source, destination)
    return destination


def _copy_application(target: Path) -> None:
    """Copy the application itself into the staged tree."""
    for source_name, target_name in APP_SOURCE_DIRS:
        source = PROJECT_ROOT / source_name
        if not source.is_dir():
            raise RuntimeError(
                f"{source} is missing. Build the front end before staging the "
                "runtime."
            )
        shutil.copytree(
            source,
            target / target_name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        print(f"[buildruntime] Staged {source_name}")

    # backend is a package in the installed layout, as it is in a checkout.
    (target / "backend" / "__init__.py").touch()
    shutil.copy2(
        PROJECT_ROOT / "backend" / "config.yaml",
        target / "backend" / "config.yaml",
    )

    for name in APP_FILES:
        source = PROJECT_ROOT / name
        if source.is_file():
            shutil.copy2(source, target / name)


def _archive(target: Path, version: str) -> Path:
    """Write the staged tree out as one archive and return its path."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    archive = DIST_DIR / RUNTIME_ARCHIVE_NAME
    if archive.exists():
        archive.unlink()

    files = [path for path in target.rglob("*") if path.is_file()]
    print(f"[buildruntime] Archiving {len(files)} files for {version}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(target).as_posix())
    return archive


def build_runtime() -> None:
    """Stage the deployment and archive it."""
    if os.name != "nt":
        raise RuntimeError("The Windows deployment is staged on Windows.")

    version = read_version()
    build_id = write_build_id()
    print(f"[buildruntime] Staging {APP_SHORT_NAME} v{version} ({build_id})")

    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    _copy_interpreter(RUNTIME_DIR)
    _install_dependencies(RUNTIME_DIR)
    saved = _prune_qt(RUNTIME_DIR)
    print(f"[buildruntime] Pruned unused Qt modules, saving {saved} MB")
    exe = _name_the_executable(RUNTIME_DIR)
    print(f"[buildruntime] Application executable: {exe.name}")
    _copy_application(RUNTIME_DIR)

    archive = _archive(RUNTIME_DIR, version)
    tree_mb = _directory_bytes(RUNTIME_DIR) / BYTES_PER_MB
    archive_mb = archive.stat().st_size / BYTES_PER_MB
    print(
        f"[buildruntime] Staged tree: {tree_mb:.0f} MB, "
        f"archive: {archive_mb:.0f} MB at {archive}"
    )


def main() -> int:
    try:
        build_runtime()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[buildruntime] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
