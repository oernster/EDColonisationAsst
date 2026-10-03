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
  counts exactly as one at module level. Every spelling counts too:
  `from .. import api`, the absolute `src.` and `backend.src.` forms and a
  literal `importlib.import_module` or `__import__`. The plants below prove
  each one is caught.
* **Isolation of the setup program.** `installer/` and `installer_main.py`
  import nothing from `backend/`, which is what keeps the compiled onefile down
  to PySide6 plus the standard library.
* **Module size.** No file over `_MAX_LINES` lines. The rule arrived with an
  allowlist of the files that were already over it; that list is now empty and
  gone with it, so the cap applies to every scanned file without exception.

The size scan covers TypeScript as well as Python, which is what caught the
front end at all: a scan walking `*.py` only would have reported a clean
repository while `FleetCarriersPanel.tsx` sat at 752 lines. TypeScript is
measured but not parsed: the import rules are Python only.

Delivery scripts (`buildexe.py`, `buildinstaller.py`) are deliberately outside
every scan here. They are linear recipes read top to bottom, where splitting a
sequence of flags and steps across modules costs more than it buys. Do not add
them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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

    Every spelling counts: `from .. import api` names the module `api` it
    imports, not just the package it imports from; the absolute `src.` and
    `backend.src.` spellings are reported with that prefix (see `_top_level`);
    `importlib.import_module`, a bare `import_module` and `__import__` called
    with a literal name count as imports of that name.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = path.relative_to(package_root).with_suffix("").parts[:-1]

    def resolve(level: int, module: str | None) -> str:
        if not level:
            return module or ""
        base = package[: len(package) - (level - 1)]
        suffix = tuple(module.split(".")) if module else ()
        return ".".join(base + suffix)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            source = resolve(node.level, node.module)
            if source:
                yield source
            for alias in node.names:
                yield f"{source}.{alias.name}" if source else alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.Call):
            name = _dynamic_import_name(node)
            if name:
                level = len(name) - len(name.lstrip("."))
                yield resolve(level, name.lstrip(".") or None)


# The callables that import a module named by a string.
_DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})


def _dynamic_import_name(call: ast.Call) -> str | None:
    """The literal module name a dynamic import call names, if it names one."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in _DYNAMIC_IMPORTERS or not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


# How the backend's own packages are spelt from outside them: a checkout runs
# with `backend/` on the path (`src.api`), the installed runtime with the root
# on it (`backend.src.api`). Both address the same layer as a relative import.
_ABSOLUTE_BACKEND_PREFIXES = ("backend.src.", "src.")


def _top_level(module: str) -> str:
    for prefix in _ABSOLUTE_BACKEND_PREFIXES:
        if module.startswith(prefix):
            module = module[len(prefix) :]
            break
    return module.split(".", 1)[0]


def _backend_top_level_names(src_root: Path) -> set[str]:
    """Every name that addresses something inside `backend/src`."""
    names = set()
    for entry in src_root.iterdir():
        if entry.name.startswith("_"):
            continue
        if entry.is_dir():
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


def _layer_violations(src_root: Path) -> list[str]:
    violations = []
    for package, forbidden in sorted(_FORBIDDEN_BACKEND_IMPORTS.items()):
        for path in _python_files(src_root / package):
            for module in _imported_modules(path, src_root):
                if _top_level(module) in forbidden:
                    violations.append(f"{path.name} imports {module}")
    return sorted(violations)


def _models_violations(src_root: Path) -> list[str]:
    forbidden = _backend_top_level_names(src_root) - {_MODELS_PACKAGE}
    violations = []
    for path in _python_files(src_root / _MODELS_PACKAGE):
        for module in _imported_modules(path, src_root):
            if _top_level(module) in forbidden:
                violations.append(f"{path.name} imports {module}")
    return sorted(violations)


def _setup_program_violations(root: Path) -> list[str]:
    paths = [root / _SETUP_PROGRAM_ENTRY]
    paths.extend(_python_files(root / _SETUP_PROGRAM_PACKAGE))
    violations = []
    for path in paths:
        for module in _imported_modules(path, root):
            # The raw first segment: here `backend` and `src` ARE the names
            # that must not appear, so no prefix is stripped.
            if module.split(".", 1)[0] in _APPLICATION_ROOTS:
                violations.append(f"{path.name} imports {module}")
    return sorted(violations)


def test_backend_layers_import_only_inwards():
    violations = _layer_violations(_BACKEND_SRC)
    assert not violations, "Imports against the layer direction:\n" + "\n".join(
        violations
    )


def test_models_import_nothing_else_from_the_backend():
    violations = _models_violations(_BACKEND_SRC)
    assert not violations, (
        "models is the innermost layer and must import nothing else "
        "from the backend:\n" + "\n".join(violations)
    )


def test_the_setup_program_imports_nothing_from_the_application():
    violations = _setup_program_violations(_ROOT)
    message = "The setup program must not import the application it ships:\n"
    assert not violations, message + "\n".join(violations)


# ------------------------------------------------------------- plants
#
# The guards above are only as good as the spellings they recognise. Each
# plant below is an import against the rules written a different way; every
# one must be reported. Before these existed the walk missed `from .. import`,
# the `src.` and `backend.src.` absolute spellings (the second is used across
# the runtime layer) and importlib, so each could cross a layer unseen.

_LAYER_PLANTS = (
    "from .. import api",
    "from src.api import routes",
    "from backend.src.runtime import tray_ui",
    "import src.api.routes",
    "import importlib\nimportlib.import_module('src.api.routes')",
    "from importlib import import_module\nimport_module('backend.src.runtime')",
    "import importlib\nimportlib.import_module('..api', package=__package__)",
    "__import__('src.api')",
)

_MODELS_PLANTS = (
    "from .. import config",
    "from src.services import journal_parser",
    "from backend.src.utils import logger",
)

_SETUP_PROGRAM_PLANTS = (
    "import importlib\nimportlib.import_module('backend.src.main')",
    "__import__('src.config')",
)


def _backend_tree(root: Path) -> Path:
    src = root / "src"
    for package in ("api", "services", "repositories", "models", "runtime", "utils"):
        (src / package).mkdir(parents=True)
        (src / package / "__init__.py").write_text("", encoding="utf-8")
    (src / "config.py").write_text("", encoding="utf-8")
    return src


@pytest.mark.parametrize("plant", _LAYER_PLANTS)
def test_every_spelling_of_an_outward_import_is_caught(tmp_path, plant):
    src = _backend_tree(tmp_path)
    (src / "services" / "plant.py").write_text(plant + "\n", encoding="utf-8")

    assert _layer_violations(src), plant


@pytest.mark.parametrize("plant", _MODELS_PLANTS)
def test_every_spelling_of_a_models_import_is_caught(tmp_path, plant):
    src = _backend_tree(tmp_path)
    (src / "models" / "plant.py").write_text(plant + "\n", encoding="utf-8")

    assert _models_violations(src), plant


@pytest.mark.parametrize("plant", _SETUP_PROGRAM_PLANTS)
def test_every_spelling_of_a_setup_program_import_is_caught(tmp_path, plant):
    (tmp_path / _SETUP_PROGRAM_PACKAGE).mkdir()
    (tmp_path / _SETUP_PROGRAM_ENTRY).write_text("", encoding="utf-8")
    (tmp_path / _SETUP_PROGRAM_PACKAGE / "plant.py").write_text(
        plant + "\n", encoding="utf-8"
    )

    assert _setup_program_violations(tmp_path), plant


def test_inward_imports_are_not_reported(tmp_path):
    src = _backend_tree(tmp_path)
    (src / "services" / "clean.py").write_text(
        "from . import sibling\n"
        "from ..models import colonisation\n"
        "from src.repositories import colonisation_repository\n"
        "import importlib\n"
        "importlib.import_module('json')\n"
        "importlib.import_module(name)\n",
        encoding="utf-8",
    )

    assert _layer_violations(src) == []


def test_modules_within_line_limit():
    offenders = []
    for path in _scanned_files():
        lines = _line_count(path)
        if lines > _MAX_LINES:
            offenders.append(f"{_rel(path)}: {lines} lines (limit {_MAX_LINES})")
    assert not offenders, "Files over the line limit (decompose them):\n" + "\n".join(
        sorted(offenders)
    )
