"""The EDCA setup program.

A self-contained PySide6 installer, compiled into a single executable by
buildinstaller.py. The package is split so the privileged work is measurable:

- ``ops`` and ``state`` hold every side effect (payload copying, shortcuts,
  registry writes, process control) and import no Qt, so they are unit tested
  and held at 100% coverage;
- ``shared`` holds resource resolution and crash logging, and imports no Qt
  either;
- ``ui`` holds the themed window and dialogs and is the only Qt client;
- ``app`` is the composition root, wiring the two halves together.

The entry point is installer_main.py at the repository root rather than a
script inside this directory: a script is compiled with its own directory on
the module search path, so compiling installer/app.py directly would leave the
``installer.*`` imports unresolvable.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations
