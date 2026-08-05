"""Putting the payload on disk, and taking it off again.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from fakes import LinkChecker, RecordingProgress

from installer.ops.copy_tree import (
    copy_tree,
    count_files,
    delete_tree,
    deployed_name,
    is_link,
    safe_destination,
)
from installer.ops.errors import UnsafePayloadEntryError
from installer.ops.progress import (
    COPY_END_PCT,
    COPY_START_PCT,
    DELETE_END_PCT,
    DELETE_START_PCT,
)

_TEXT = "bundled"


def _tree(root: Path) -> Path:
    """Stage a small payload: two files, one nested and one staged source."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.txt").write_text(_TEXT, encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "b.py_").write_text(_TEXT, encoding="utf-8")
    return root


def test_a_staged_source_is_installed_under_its_real_extension() -> None:
    assert deployed_name("main.py_") == "main.py"


def test_any_other_name_is_installed_unchanged() -> None:
    assert deployed_name("index.html") == "index.html"


def test_count_files_counts_what_the_copy_would_write(tmp_path: Path) -> None:
    source = _tree(tmp_path / "payload")

    assert count_files(source) == 2


def test_count_files_prunes_the_directories_the_copy_prunes(tmp_path: Path) -> None:
    source = _tree(tmp_path / "payload")
    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "stale.pyc").write_bytes(b"x")

    assert count_files(source) == 2


def test_safe_destination_accepts_the_target_itself(tmp_path: Path) -> None:
    assert safe_destination(tmp_path, tmp_path) == tmp_path.resolve()


def test_safe_destination_refuses_a_path_that_leaves_the_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "install"
    target.mkdir()

    with pytest.raises(UnsafePayloadEntryError):
        safe_destination(target, target / ".." / "escaped.txt")


def test_copy_tree_writes_every_file_and_restores_the_extensions(
    tmp_path: Path,
) -> None:
    source = _tree(tmp_path / "payload")
    target = tmp_path / "install"

    copied = copy_tree(source, target)

    assert copied == 2
    assert (target / "a.txt").read_text(encoding="utf-8") == _TEXT
    assert (target / "nested" / "b.py").is_file()


def test_copy_tree_prunes_the_development_directories(tmp_path: Path) -> None:
    source = _tree(tmp_path / "payload")
    tests_dir = source / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("x", encoding="utf-8")

    copy_tree(source, target := tmp_path / "install")

    assert not (target / "tests").exists()


def test_copy_tree_reports_progress_across_the_phase(tmp_path: Path) -> None:
    source = _tree(tmp_path / "payload")
    progress = RecordingProgress()

    copy_tree(source, tmp_path / "install", progress=progress)

    assert progress.percentages[0] == COPY_START_PCT
    assert progress.percentages[-1] == COPY_END_PCT


def test_copy_tree_reports_the_phase_end_for_an_empty_payload(
    tmp_path: Path,
) -> None:
    source = tmp_path / "payload"
    source.mkdir()
    progress = RecordingProgress()

    copy_tree(source, tmp_path / "install", progress=progress, total=0)

    assert progress.percentages[-1] == COPY_END_PCT


def test_copy_tree_skips_a_linked_file(tmp_path: Path) -> None:
    """A link is the one way a walked copy can write outside its target."""
    source = _tree(tmp_path / "payload")
    checker = LinkChecker([source / "a.txt"])

    copied = copy_tree(source, tmp_path / "install", link_check=checker)

    assert copied == 1
    assert not (tmp_path / "install" / "a.txt").exists()


def test_copy_tree_does_not_descend_into_a_linked_directory(tmp_path: Path) -> None:
    source = _tree(tmp_path / "payload")
    checker = LinkChecker([source / "nested"])

    copied = copy_tree(source, tmp_path / "install", link_check=checker)

    assert copied == 1
    assert not (tmp_path / "install" / "nested").exists()


def test_the_real_link_check_answers_for_an_ordinary_file(tmp_path: Path) -> None:
    ordinary = tmp_path / "a.txt"
    ordinary.write_text(_TEXT, encoding="utf-8")

    assert is_link(ordinary) is False


def test_delete_tree_does_nothing_when_the_directory_has_gone(
    tmp_path: Path,
) -> None:
    progress = RecordingProgress()

    delete_tree(tmp_path / "absent", progress=progress)

    assert progress.updates == []


def test_delete_tree_removes_everything_and_reports_progress(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path / "install")
    progress = RecordingProgress()

    delete_tree(root, progress=progress)

    assert not root.exists()
    assert progress.percentages[0] == DELETE_START_PCT
    assert progress.percentages[-1] == DELETE_END_PCT


def test_delete_tree_leaves_what_it_cannot_remove(tmp_path: Path) -> None:
    """The caller defers the remains rather than failing the uninstall here."""
    root = _tree(tmp_path / "install")
    locked = root / "nested" / "b.py_"
    locked.chmod(stat.S_IREAD)
    try:
        delete_tree(root)

        assert locked.exists()
        assert root.exists()
    finally:
        locked.chmod(stat.S_IWRITE)
