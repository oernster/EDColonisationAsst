"""Structural tests: the shape the architecture documents describe, asserted.

`ARCHITECTURE_1_backend.md` describes a backend of `api`, `services`,
`repositories`, `models`, `runtime`, `config` and `utils`; section 3 of
`ARCHITECTURE.md` states that the setup program imports nothing from the
application it ships. Until this file existed nothing enforced either
statement, so the shape held by habit rather than by rule.

Three things are asserted here.

* **Import direction.** `models` is the innermost layer and imports nothing
  else from the backend. `repositories` stays free of `api`, `services` and
  `runtime`; `services` stays free of `api` and `runtime`; `api` stays free of
  `runtime`. `IColonisationRepository` already designs that seam; this is what
  guards it. The scan is an AST walk, so an import deferred inside a function
  counts exactly as one at module level.
* **Isolation of the setup program.** `installer/` and `installer_main.py`
  import nothing from `backend/`, which is what keeps the compiled onefile down
  to PySide6 plus the standard library.
* **Module size.** No file over `_MAX_LINES` lines outside an explicit
  allowlist of the files that were already over it when this rule arrived.

The size scan covers TypeScript as well as Python. Four of the files over the
limit are front-end components, so a scan that walked `*.py` only would report
a clean repository while `FleetCarriersPanel.tsx` sat at 752 lines. TypeScript
is measured but not parsed: the import rules are Python only.

Delivery scripts (`buildexe.py`, `buildinstaller.py`) are deliberately outside
every scan here. They are linear recipes read top to bottom, where splitting a
sequence of flags and steps across modules costs more than it buys. Do not add
them.
"""

from __future__ import annotations

import ast
from pathlib import Path

_MAX_LINES = 400
_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_SRC = _ROOT / "backend" / "src"

# Every backend package a module may not reach into, keyed by the package doing
# the importing. Read each entry as "this layer stays free of these".
_FORBIDDEN_BACKEND_IMPORTS = {
    "repositories": ("api", "services", "runtime"),
    "services": ("api", "runtime"),
    "api": ("runtime",),
}

# The innermost layer: it may import its own siblings and nothing else from the
# backend.
_MODELS_PACKAGE = "models"

# The setup program is a second program that ships the first, so these are the
# names it may never import.
_APPLICATION_ROOTS = ("backend", "src")

_SETUP_PROGRAM_ENTRY = "installer_main.py"
_SETUP_PROGRAM_PACKAGE = "installer"

_SIZE_SCAN_TREES = (
    "backend/src",
    "backend/tests",
    "backend/tools",
    "installer",
    "tests",
    "frontend/src",
)
_SIZE_SCAN_MODULES = (_SETUP_PROGRAM_ENTRY,)
_SIZE_SCAN_SUFFIXES = (".py", ".ts", ".tsx")

# Files already over the limit when this rule was introduced. Tracked debt: this
# set may only shrink. Do not add to it; decompose new code instead.
# `test_legacy_allowlist_has_no_stale_entries` fails if an entry is no longer
# over the limit or no longer exists, so an entry cannot outlive its file.
_LEGACY_OVER_LIMIT = frozenset(
    {
        # Backend source. app_runtime.py is the one to take next: it is the
        # largest remaining file here and the seams are already implied by its
        # own tests.
        "backend/src/runtime/app_runtime.py",
        "backend/src/services/journal_parser.py",
        "backend/src/repositories/colonisation_repository.py",
        "backend/src/main.py",
        "backend/src/runtime/launcher_components.py",
        # Front end. useKeepAwake.ts shows the project already knows how to
        # move state out of a component and into a hook.
        "frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx",
        "frontend/src/components/SiteList/SiteList.tsx",
        "frontend/src/hooks/useKeepAwake.ts",
    }
)


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _python_files(tree: Path):
    for path in sorted(tree.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _scanned_files():
    for tree in _SIZE_SCAN_TREES:
        for path in sorted((_ROOT / tree).rglob("*")):
            if path.suffix in _SIZE_SCAN_SUFFIXES and "__pycache__" not in path.parts:
                yield path
    for module in _SIZE_SCAN_MODULES:
        yield _ROOT / module


def _imported_modules(path: Path, package_root: Path):
    """Dotted module names imported by `path`, resolved against `package_root`.

    Relative imports are resolved the way Python resolves them, so
    `from ..models.carriers import X` inside `api/carriers.py` reads as
    `models.carriers` rather than as an unresolvable dot prefix.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = path.relative_to(package_root).with_suffix("").parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                suffix = tuple(node.module.split(".")) if node.module else ()
                yield ".".join(base + suffix)
            elif node.module:
                yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _top_level(module: str) -> str:
    return module.split(".", 1)[0]


def _backend_top_level_names() -> set[str]:
    """Every name that addresses something inside `backend/src`."""
    names = set()
    for entry in _BACKEND_SRC.iterdir():
        if entry.name.startswith("_"):
            continue
        if entry.is_dir():
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


def test_backend_layers_import_only_inwards():
    violations = []
    for package, forbidden in sorted(_FORBIDDEN_BACKEND_IMPORTS.items()):
        for path in _python_files(_BACKEND_SRC / package):
            for module in _imported_modules(path, _BACKEND_SRC):
                if _top_level(module) in forbidden:
                    violations.append(f"{_rel(path)} imports {module}")
    assert not violations, "Imports against the layer direction:\n" + "\n".join(
        sorted(violations)
    )


def test_models_import_nothing_else_from_the_backend():
    forbidden = _backend_top_level_names() - {_MODELS_PACKAGE}
    violations = []
    for path in _python_files(_BACKEND_SRC / _MODELS_PACKAGE):
        for module in _imported_modules(path, _BACKEND_SRC):
            if _top_level(module) in forbidden:
                violations.append(f"{_rel(path)} imports {module}")
    assert not violations, (
        "models is the innermost layer and must import nothing else "
        "from the backend:\n" + "\n".join(sorted(violations))
    )


def test_the_setup_program_imports_nothing_from_the_application():
    paths = [_ROOT / _SETUP_PROGRAM_ENTRY]
    paths.extend(_python_files(_ROOT / _SETUP_PROGRAM_PACKAGE))
    violations = []
    for path in paths:
        for module in _imported_modules(path, _ROOT):
            if _top_level(module) in _APPLICATION_ROOTS:
                violations.append(f"{_rel(path)} imports {module}")
    message = "The setup program must not import the application it ships:\n"
    assert not violations, message + "\n".join(sorted(violations))


def test_modules_within_line_limit():
    offenders = []
    for path in _scanned_files():
        rel = _rel(path)
        if rel in _LEGACY_OVER_LIMIT:
            continue
        lines = _line_count(path)
        if lines > _MAX_LINES:
            offenders.append(f"{rel}: {lines} lines (limit {_MAX_LINES})")
    assert not offenders, "Files over the line limit (decompose them):\n" + "\n".join(
        sorted(offenders)
    )


def test_legacy_allowlist_has_no_stale_entries():
    stale = []
    for rel in sorted(_LEGACY_OVER_LIMIT):
        path = _ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: missing (remove from allowlist)")
        elif _line_count(path) <= _MAX_LINES:
            stale.append(f"{rel}: now within limit (remove from allowlist)")
    assert not stale, "Stale legacy allowlist entries:\n" + "\n".join(stale)
