"""Configuration management for the application"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings
import yaml

from .constants import DEFAULT_BACKEND_PORT

# Load .env file at the top level of the module
load_dotenv()


def _default_journal_directory() -> str:
    """Where the journals are, worked out rather than assumed.

    This used to be a hardcoded literal containing `%USERNAME%`, which is a
    cmd.exe variable that nothing in Python expands, so it named a directory
    that could not exist on any machine. Detection has always been available;
    it simply was not used here.

    The import is deliberately late. utils/__init__ pulls in the logger and the
    logger imports this module, so importing it at the top would be circular.
    """
    from .utils.journal import find_journal_directory

    detected = find_journal_directory()
    if detected is not None:
        return str(detected)

    # Detection only fails when the game has not written journals yet. Name
    # the standard location so the watcher has somewhere to look once it does.
    saved_games = Path.home() / "Saved Games" / "Frontier Developments"
    return str(saved_games / "Elite Dangerous")


class JournalConfig(BaseSettings):
    """Journal file configuration"""

    directory: str = Field(
        default_factory=_default_journal_directory,
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
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    inara: InaraConfig = Field(default_factory=InaraConfig)


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

    - A source checkout keeps using its own tree:
        backend/config.yaml
        backend/commander.yaml

    - Every packaged runtime (frozen, flatpak or an installed deployment)
      keeps them in the per-user configuration directory. The install tree
      is the wrong place on every one of them: a flatpak's ``/app`` is
      read-only and the Windows setup program overwrites every file of the
      runtime archive, the shipped ``backend/config.yaml`` included, on each
      upgrade, reinstall and repair. Keeping the user's file there lost the
      saved journal folder and any host, port or CORS edit every time. No
      seed is copied in: an absent file means defaults (which are what the
      shipped file holds); the first save creates it.
    """
    # Late for the same reason as the import in _default_journal_directory: a
    # top-level import of anything under utils would be circular. By call time
    # utils is fully imported. This keeps one definition of "packaged".
    from .utils.runtime import is_packaged

    if is_packaged():
        base_dir = _get_user_config_dir()
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

        # The commander's name is journal-derived now. Installs that saved
        # settings before that change still carry the key in commander.yaml,
        # and InaraConfig forbids unknown fields, so drop it before validating.
        inara_dict = dict(commander_dict.get("inara", {}))
        inara_dict.pop("commander_name", None)
        inara_cfg = InaraConfig(**inara_dict)

        _config = AppConfig(
            journal=JournalConfig(**config_dict.get("journal", {})),
            server=ServerConfig(**config_dict.get("server", {})),
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
