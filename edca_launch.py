"""Start EDCA from an installed deployment.

An installed EDCA is a plain interpreter over plain sources rather than a
compiled executable, so something has to do the two things a frozen build got
for free: put the install directory on the module search path and say that this
is an installed layout rather than a developer's checkout.

This script is what the shortcuts and the sign-in entry run. It is deliberately
tiny and imports nothing of the application until both facts are established.
British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Read by backend.src.utils.runtime.is_deployed. It has to be set before the
# application is imported, since modules decide where they write from it.
ENV_DEPLOYED = "EDCA_PACKAGED"
ENV_DEPLOYED_VALUE = "1"


def prepare(root: Path) -> None:
    """Make an installed layout importable and declare that it is installed."""
    os.environ.setdefault(ENV_DEPLOYED, ENV_DEPLOYED_VALUE)
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def main() -> int:
    """Run the application, answering its exit code."""
    prepare(Path(__file__).resolve().parent)

    from backend.src.runtime_entry import main as runtime_main

    return runtime_main()


if __name__ == "__main__":
    raise SystemExit(main())
