"""Tests for what the startup splash is told while it waits.

Two things are pinned here. The arithmetic, because a progress bar that
measured files rather than bytes would lurch (journal files differ in size by
more than an order of magnitude), and the wording, because the splash lives in
backend/src/runtime which is outside the coverage gate, so the decisions about
what to say were deliberately put in the service where they can be tested.

The recurring rule is that silence is a valid answer. None means "keep showing
whatever you were showing", which is what a splash should do when the backend
cannot yet say anything useful.
"""

from __future__ import annotations

from backend.src.services.startup_progress import (
    BYTES_PER_MB,
    StartupProgressTracker,
    StartupSnapshot,
    StartupStage,
    startup_explanation,
    startup_progress_message,
)


def test_a_fresh_tracker_has_not_started() -> None:
    """Before anything happens there is nothing to report."""
    snapshot = StartupProgressTracker().snapshot()

    assert snapshot.stage is StartupStage.STARTING
    assert snapshot.files_total == 0
    assert snapshot.percent is None


def test_beginning_an_import_publishes_the_totals_up_front() -> None:
    """The whole point: the denominator is known before the work starts."""
    tracker = StartupProgressTracker()
    tracker.begin_import([BYTES_PER_MB, 3 * BYTES_PER_MB])

    snapshot = tracker.snapshot()
    assert snapshot.stage is StartupStage.IMPORTING_JOURNALS
    assert snapshot.files_total == 2
    assert snapshot.bytes_total == 4 * BYTES_PER_MB
    assert snapshot.files_done == 0
    assert snapshot.percent == 0


def test_progress_is_measured_in_bytes_not_files() -> None:
    """One of two files done is not half the work when sizes differ."""
    tracker = StartupProgressTracker()
    tracker.begin_import([BYTES_PER_MB, 3 * BYTES_PER_MB])

    tracker.file_imported(BYTES_PER_MB)

    snapshot = tracker.snapshot()
    assert snapshot.files_done == 1
    # Half the files, a quarter of the bytes. The bar shows the quarter.
    assert snapshot.percent == 25


def test_a_file_that_failed_to_parse_still_counts() -> None:
    """It took its share of the wait, so a bar must not stall on it."""
    tracker = StartupProgressTracker()
    tracker.begin_import([BYTES_PER_MB, BYTES_PER_MB])
    tracker.file_imported(BYTES_PER_MB)
    tracker.file_imported(BYTES_PER_MB)

    assert tracker.snapshot().percent == 100


def test_a_negative_size_cannot_wind_the_bar_backwards() -> None:
    """Sizes come from the filesystem, so be blunt about the impossible."""
    tracker = StartupProgressTracker()
    tracker.begin_import([BYTES_PER_MB])
    tracker.file_imported(-BYTES_PER_MB)

    assert tracker.snapshot().bytes_done == 0


def test_progress_is_clamped_to_the_total() -> None:
    """Files can grow between being measured and being read."""
    tracker = StartupProgressTracker()
    tracker.begin_import([BYTES_PER_MB])
    tracker.file_imported(5 * BYTES_PER_MB)

    assert tracker.snapshot().percent == 100


def test_percent_is_unknowable_without_a_total() -> None:
    """An import of nothing has no meaningful completion, so it says so."""
    tracker = StartupProgressTracker()
    tracker.begin_import([])

    assert tracker.snapshot().percent is None


def test_the_catch_up_path_reports_itself() -> None:
    """The repeat-run path is a different stage with a different line."""
    tracker = StartupProgressTracker()
    tracker.begin_catch_up()

    assert tracker.snapshot().stage is StartupStage.CATCHING_UP


def test_finishing_marks_startup_ready() -> None:
    """A splash left on 'catching up' would be lying about the wait."""
    tracker = StartupProgressTracker()
    tracker.begin_catch_up()
    tracker.finish()

    assert tracker.snapshot().stage is StartupStage.READY


def test_the_import_line_names_the_file_being_read() -> None:
    """The file in hand, not the count finished, so it never opens at zero."""
    snapshot = StartupSnapshot(
        stage=StartupStage.IMPORTING_JOURNALS,
        files_done=34,
        files_total=72,
        bytes_done=31 * BYTES_PER_MB,
        bytes_total=67 * BYTES_PER_MB,
    )

    # 34 finished means the 35th is the one being read.
    assert startup_progress_message(snapshot) == (
        "Reading journal 35 of 72 (31 MB of 67 MB)"
    )


def test_the_import_line_opens_at_one_rather_than_zero() -> None:
    """Nothing read yet still means a first journal is in hand."""
    snapshot = StartupSnapshot(
        stage=StartupStage.IMPORTING_JOURNALS,
        files_total=72,
        bytes_total=67 * BYTES_PER_MB,
    )

    assert startup_progress_message(snapshot) == (
        "Reading journal 1 of 72 (0 MB of 67 MB)"
    )


def test_the_last_journal_does_not_read_as_one_past_the_total() -> None:
    """Every file done, before the stage flips, must still be in range."""
    snapshot = StartupSnapshot(
        stage=StartupStage.IMPORTING_JOURNALS,
        files_done=72,
        files_total=72,
        bytes_done=67 * BYTES_PER_MB,
        bytes_total=67 * BYTES_PER_MB,
    )

    assert startup_progress_message(snapshot) == (
        "Reading journal 72 of 72 (67 MB of 67 MB)"
    )


def test_a_small_import_does_not_advertise_zero_megabytes() -> None:
    """Rounding a handful of kilobytes down would read as '0 MB of 0 MB'."""
    snapshot = StartupSnapshot(
        stage=StartupStage.IMPORTING_JOURNALS,
        files_done=1,
        files_total=2,
        bytes_done=1024,
        bytes_total=2048,
    )

    assert startup_progress_message(snapshot) == "Reading journal 2 of 2..."


def test_an_import_with_no_files_counted_still_says_something() -> None:
    """Between starting the import and measuring it, the line stays honest."""
    snapshot = StartupSnapshot(stage=StartupStage.IMPORTING_JOURNALS)

    assert startup_progress_message(snapshot) == "Reading your journals..."


def test_the_catch_up_line_says_what_it_is_doing() -> None:
    """The repeat-run path is quick, but it should still name itself."""
    snapshot = StartupSnapshot(stage=StartupStage.CATCHING_UP)

    assert startup_progress_message(snapshot) == "Catching up on your recent flights..."


def test_the_other_stages_say_nothing_and_mean_it() -> None:
    """Silence leaves the splash's own wording in place, which is better."""
    assert (
        startup_progress_message(StartupSnapshot(stage=StartupStage.STARTING)) is None
    )
    assert startup_progress_message(StartupSnapshot(stage=StartupStage.READY)) is None


def test_only_the_first_run_import_explains_itself() -> None:
    """It is the one slow path, slow for a reason nobody could guess."""
    explanation = startup_explanation(
        StartupSnapshot(stage=StartupStage.IMPORTING_JOURNALS)
    )

    assert explanation is not None
    assert "First run only" in explanation


def test_the_quick_paths_offer_no_excuse() -> None:
    """Explaining a wait that is not happening is just noise."""
    assert startup_explanation(StartupSnapshot(stage=StartupStage.CATCHING_UP)) is None
    assert startup_explanation(StartupSnapshot(stage=StartupStage.READY)) is None
