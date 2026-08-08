"""Configuration management for the application"""

import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings
import yaml

from .constants import DEFAULT_BACKEND_PORT

# Load .env file at the top level of the module
load_dotenv()


class JournalConfig(BaseSettings):
    """Journal file configuration"""

    directory: str = Field(
        default=(
            r"C:\Users\%USERNAME%\Saved Games\Frontier Developments" "\\Elite Dangerous"
        ),
        description="Path to Elite: Dangerous journal directory",
    )
    watch_interval: float = Field(
        default=1.0, description="File watch interval in seconds"
    )


class ServerConfig(BaseSettings):
    """Server configuration"""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=DEFAULT_BACKEND_PORT, description="Server port")
    cors_origins: list[str] = Field(
        default=["http://localhost:5173"], description="Allowed CORS origins"
    )


class WebSocketConfig(BaseSettings):
    """WebSocket configuration"""

    ping_interval: int = Field(
        default=30, description="WebSocket ping interval in seconds"
    )
    reconnect_attempts: int = Field(
        default=5, description="Number of reconnection attempts"
    )


class LoggingConfig(BaseSettings):
    """Logging configuration"""

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string",
    )


class InaraConfig(BaseSettings):
    """Inara API configuration"""

    api_key: str = os.getenv("INARA_API_KEY", "")
    commander_name: str | None = os.getenv("INARA_COMMANDER_NAME")
    app_name: str = os.getenv("INARA_APP_NAME", "")
    prefer_local_for_commander_systems: bool = Field(
        default=True,
        description=(
            "When true (default), systems where this commander's journals contain "
            "colonisation sites are served purely from local journal data. Inara is "
            "only consulted for systems with no local colonisation data. When false, "
            "Inara data is preferred wherever it is available."
        ),
    )


class AppConfig(BaseSettings):
    """Main application configuration"""

    journal: JournalConfig = Field(default_factory=JournalConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    inara: InaraConfig = Field(default_factory=InaraConfig)


def _is_frozen() -> bool:
    """
    Return True if the current process is a frozen executable.

    This mirrors the logic in utils.runtime.is_frozen() but is kept local to
    avoid import-time dependencies from this low-level config module.
    """
    # Primary detection: explicit flag set by freezer.
    if bool(getattr(sys, "frozen", False)):
        return True

    # Fallback: argv[0] points at a non-Python .exe
    try:
        exe_path = Path(sys.argv[0])
        if exe_path.suffix.lower() == ".exe" and not exe_path.stem.lower().startswith(
            "python"
        ):
            return True
    except (TypeError, ValueError):
        # sys.argv[0] is not always a usable path string: an embedded host can
        # leave it empty or non-string (TypeError); a null byte in it
        # raises ValueError. Either way we cannot tell, so report not frozen,
        # which is the safe answer because it keeps the source layout.
        return False

    return False


def _get_user_config_dir() -> Path:
    """
    Return the per-user configuration directory for the packaged runtime.

    On Windows this resolves to %APPDATA%\\EDColonisationAsst.
    On other platforms it follows the XDG base directory spec or falls back
    to ~/.config/EDColonisationAsst.
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata)
        else:
            # Pragmatic fallback if APPDATA is missing for some reason.
            base = Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path.home() / ".config"

    return base / "EDColonisationAsst"


def get_config_paths() -> tuple[Path, Path]:
    """
    Compute the locations of config.yaml and commander.yaml.

    - In development (non-frozen) mode we keep using the source layout:
        backend/config.yaml
        backend/commander.yaml

    - In the packaged (frozen) runtime we store configuration alongside
      the installed executable so that the DB, logs and config all live
      under the single install directory (e.g. AppData\\Local\\EDColonisationAssistant).
    """
    if _is_frozen():
        # Directory containing the running EXE (install root when packaged).
        try:
            base_dir = Path(sys.argv[0]).resolve().parent
        except (OSError, TypeError, ValueError):
            # As in _is_frozen, plus resolve() itself hitting the filesystem
            # (OSError). Fall back to the source layout rather than leave the
            # configuration paths undefined.
            base_dir = Path(__file__).resolve().parents[2]
    else:
        # backend/src/config.py -> src -> backend
        base_dir = Path(__file__).parent.parent

    config_path = base_dir / "config.yaml"
    commander_path = base_dir / "commander.yaml"
    return config_path, commander_path


# Global config instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        # Resolve configuration file locations in a runtime-aware way.
        # In the packaged EXE we read from a per-user writable directory
        # instead of the (potentially read-only) install location.
        config_path, commander_path = get_config_paths()

        config_dict: dict = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = yaml.safe_load(f) or {}
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                # config.yaml is hand-editable, so all three are user-caused
                # rather than defects: an unreadable file (OSError), a file
                # saved in another encoding (UnicodeDecodeError) and malformed
                # YAML (yaml.YAMLError, which Windows paths with backslashes
                # inside double-quoted strings produce readily). Fall back to
                # defaults rather than crash startup.
                config_dict = {}

        commander_dict: dict = {}
        if commander_path.exists():
            try:
                with open(commander_path, "r", encoding="utf-8") as f:
                    commander_dict = yaml.safe_load(f) or {}
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                # Same three user-caused failures as config.yaml above.
                # commander.yaml only carries Inara credentials, so defaults
                # mean "not configured" rather than a broken application.
                commander_dict = {}

        inara_cfg = InaraConfig(**commander_dict.get("inara", {}))

        _config = AppConfig(
            journal=JournalConfig(**config_dict.get("journal", {})),
            server=ServerConfig(**config_dict.get("server", {})),
            websocket=WebSocketConfig(**config_dict.get("websocket", {})),
            logging=LoggingConfig(**config_dict.get("logging", {})),
            inara=inara_cfg,
        )

        # Expand env vars in journal directory (works for $VAR / ${VAR} style on POSIX)
        _config.journal.directory = os.path.expandvars(_config.journal.directory)

        # Linux auto-detection: the default config value is Windows-centric.
        # If we're not on Windows and the configured directory doesn't exist (or still
        # looks like the Windows default), attempt to detect Steam Proton/Wine paths.
        if os.name != "nt":
            configured_str = _config.journal.directory
            looks_like_windows_default = (
                "%USERNAME%" in configured_str
                or configured_str.startswith(("C:\\", "C:/"))
            )

            configured_path = Path(configured_str)
            # Only auto-detect when the configured value still looks like the baked-in
            # Windows default and it doesn't exist on this platform.
            #
            # If the user explicitly sets a POSIX path that doesn't exist yet, we
            # should not silently override it.
            if looks_like_windows_default and not configured_path.exists():
                try:
                    from .utils.journal import (
                        find_journal_directory,
                    )  # noqa: WPS433 (late import)

                    detected = find_journal_directory()
                    if detected is not None:
                        _config.journal.directory = str(detected)
                except Exception:  # noqa: BLE001, S110
                    # Deliberately broad. find_journal_directory probes Steam,
                    # Proton and Wine layouts across distributions, so its
                    # failure modes are open-ended and not worth enumerating.
                    # The configured directory simply stays as it was, which
                    # the settings page lets the user correct. Never block
                    # startup on best-effort detection logic.
                    pass

    return _config


def set_config(config: AppConfig) -> None:
    """Set the global configuration instance (mainly for testing)"""
    global _config
    _config = config
