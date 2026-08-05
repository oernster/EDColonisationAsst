"""Identity, layout and registry constants for the EDCA setup program.

Every name the installer writes to disk or to the registry is declared here, so
a rename is a single edit and no module carries an inline literal. British
spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

# --- product identity -------------------------------------------------------

# The display name shown in all installer text and in the Apps list.
APP_DISPLAY_NAME = "Elite: Dangerous Colonisation Assistant"
APP_TAGLINE = "Colonisation support for Commanders"
APP_PUBLISHER = "Oliver Ernster"
APP_URL = "https://oernster.github.io/EDColonisationAsst/"

# The spaceless identifier used for the per-user install directory. This is the
# historical name and must not change: an existing installation is found by it.
APP_ID = "EDColonisationAssistant"
# The short name used for the executable, the shortcuts and the registry keys.
APP_SHORT_NAME = "EDColonisationAsst"

EXE_NAME = f"{APP_SHORT_NAME}.exe"
EXE_SUFFIX = ".exe"
ICON_FILE_NAME = f"{APP_SHORT_NAME}.ico"
PNG_FILE_NAME = f"{APP_SHORT_NAME}.png"

# The runtime is started with this flag at sign-in so a login start does not
# open a browser window over whatever the user is doing.
NO_BROWSER_FLAG = "--no-browser"

# --- payload layout ---------------------------------------------------------

# Staged by buildinstaller.py. The payload is a plain directory tree rather
# than an archive, so it is copied file by file on deploy.
PAYLOAD_DIR_NAME = "payload"
BUILD_DIR_NAME = "build"
# Nuitka strips loose executables out of an included data directory, so the
# runtime is embedded a second time under its own directory and recovered from
# there when the copied payload turns out not to carry it.
RUNTIME_DIR_NAME = "runtime"
LICENSE_FILE_NAME = "LICENSE"
VERSION_FILE_NAME = "VERSION"

# Directories that are never wanted in an installed tree, pruned during the
# copy in case the payload root points at a checkout rather than a staged tree.
IGNORED_DIR_NAMES = (
    ".git",
    ".venv",
    "venv",
    ".benchmarks",
    "htmlcov",
    ".pytest_cache",
    "__pycache__",
    "tests",
    "node_modules",
)

# buildinstaller.py ships backend sources renamed so Nuitka does not strip
# them from the data directory; the copy restores the real extension.
STAGED_PY_SUFFIX = ".py_"
PY_SUFFIX = ".py"

# --- per-user locations (no administrator rights required) ------------------

ENV_LOCALAPPDATA = "LOCALAPPDATA"
ENV_APPDATA = "APPDATA"
ENV_USERPROFILE = "USERPROFILE"
ENV_PROGRAM_FILES = "PROGRAMFILES"
ENV_PROGRAM_FILES_X86 = "PROGRAMFILES(X86)"
START_MENU_SUBPATH = ("Microsoft", "Windows", "Start Menu", "Programs")
DESKTOP_DIR_NAME = "Desktop"
SHORTCUT_EXT = ".lnk"
MAC_APPS_DIR_NAME = "Applications"
LINUX_SHARE_SUBPATH = (".local", "share")

# --- the registered uninstaller ---------------------------------------------

# A copy of the setup program is placed under the install root, so
# "Apps & features" can re-run it with --uninstall.
UNINSTALLER_SUBDIR = "_uninstall"
UNINSTALLER_NAME = f"{APP_SHORT_NAME}Installer.exe"
UNINSTALL_FLAG = "--uninstall"
# Under a Nuitka onefile build sys.executable is the unpacked temporary
# bootstrap, so the original launcher is discovered through this instead.
NUITKA_ONEFILE_ENV = "NUITKA_ONEFILE_BINARY"

# --- registry keys (all under HKCU) -----------------------------------------

UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_SHORT_NAME}"
RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = APP_SHORT_NAME

# --- diagnostics ------------------------------------------------------------

# A console-disabled onefile shows no traceback when it dies, so unhandled
# exceptions are appended to this file under the temporary directory.
INSTALLER_LOG_NAME = "edca-installer.log"

# Used when the bundled VERSION file is missing or unreadable.
FALLBACK_VERSION = "0.0.0"

# --- platform detection -----------------------------------------------------

WINDOWS_PREFIX = "win"
MACOS_PLATFORM = "darwin"
