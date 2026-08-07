"""Windows specific utility functions"""

import ctypes
import os
from pathlib import Path

# Known folder IDs
FOLDERID_SavedGames = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"


class GUID(ctypes.Structure):
    # Use fixed-width integer types so the struct layout matches Windows GUIDs
    # even when running tests on non-Windows platforms (where c_ulong may be 64-bit).
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def get_saved_games_path() -> Path | None:
    """
    Get the path to the user's Saved Games folder on Windows.

    Notes:
      - On non-Windows platforms `ctypes.windll` typically does not exist.
        This function is written to be safe to import/call cross-platform and
        may legitimately return None.
    """
    # Prefer the WinAPI if available (tests monkeypatch ctypes.windll on non-Windows).
    windll = getattr(ctypes, "windll", None)
    if windll is not None:
        ptr: ctypes.c_wchar_p | None = None
        try:
            ptr = ctypes.c_wchar_p()

            folder_guid = GUID.from_buffer_copy(
                bytes.fromhex(
                    FOLDERID_SavedGames.replace("-", "")
                    .replace("{", "")
                    .replace("}", "")
                )
            )

            windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_guid),
                0,
                None,
                ctypes.byref(ptr),
            )
            path = ptr.value
            if path:
                return Path(path)
        except Exception:  # noqa: BLE001, S110
            # Deliberately broad. This is a raw ctypes call into shell32:
            # a missing symbol raises AttributeError, a bad call raises
            # OSError; a wrong argument type raises ctypes.ArgumentError,
            # which does not share a useful base with the others. Any WinAPI
            # failure falls through to USERPROFILE below, which is the whole
            # point of the fallback.
            pass
        finally:
            # Free pointer if possible; failures are non-fatal.
            try:
                if ptr is not None:
                    windll.ole32.CoTaskMemFree(ptr)
            except Exception:  # noqa: BLE001, S110
                # Deliberately broad, in a finally block. Failing to free the
                # pointer leaks a few bytes once per call; raising here would
                # replace the caller's result (or its exception) with this
                # one, which is strictly worse than the leak.
                pass

    # Fallback to user profile
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        return Path(user_profile) / "Saved Games"

    return None
