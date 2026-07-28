"""Job-Scheduler Queue-Logik — SM36/SM37-Stil Sicherheitsnetz.

Reine Dateisystem-Logik, kein DB/Docker. Queue liegt unter logs/_queue/.
Design: docs/superpowers/specs/2026-07-24-job-scheduler-design.md
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.job_dispatcher import (
    enqueue_job,
    list_jobs,
    due_jobs,
    claim_job,
    cancel_job,
    run_dispatch,
    DESTRUCTIVE_MODES,
)


def _now():
    return datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def qdir(tmp_path):
    d = tmp_path / "_queue"
    d.mkdir()
    return d


# --------------------------------------------------------------------------
# enqueue
# --------------------------------------------------------------------------
def test_enqueue_now_writes_geplant_file(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="admin-page")
    files = list(qdir.glob("*.geplant.json"))
    assert len(files) == 1
    assert job["mode"] == "option_data"
    assert job["status"] == "geplant"
    assert job["run_at"] == "2026-07-24T18:00:00Z"


def test_enqueue_later_stores_future_run_at(qdir):
    later = _now() + timedelta(hours=3)
    job = enqueue_job(qdir, mode="stock_data_daily", run_at=later, created_by="admin-page")
    assert job["run_at"] == "2026-07-24T21:00:00Z"


def test_enqueue_unique_ids(qdir):
    a = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    b = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    assert a["id"] != b["id"]
    assert len(list(qdir.glob("*.geplant.json"))) == 2


# --------------------------------------------------------------------------
# due_jobs
# --------------------------------------------------------------------------
def test_due_jobs_returns_only_past_or_now(qdir):
    enqueue_job(qdir, mode="option_data", run_at=_now() - timedelta(minutes=1), created_by="x")
    enqueue_job(qdir, mode="stock_data_daily", run_at=_now() + timedelta(hours=2), created_by="x")
    due = due_jobs(qdir, now=_now())
    assert len(due) == 1
    assert due[0]["mode"] == "option_data"


def test_due_jobs_ignores_laufend(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now() - timedelta(minutes=5), created_by="x")
    claim_job(qdir, job["id"])  # geplant -> laufend
    assert due_jobs(qdir, now=_now()) == []


def test_due_jobs_exactly_now_is_due(qdir):
    enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    assert len(due_jobs(qdir, now=_now())) == 1


# --------------------------------------------------------------------------
# claim (atomic geplant -> laufend)
# --------------------------------------------------------------------------
def test_claim_moves_geplant_to_laufend(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    claimed = claim_job(qdir, job["id"])
    assert claimed is not None
    assert claimed["status"] == "laufend"
    assert list(qdir.glob("*.geplant.json")) == []
    assert len(list(qdir.glob("*.laufend.json"))) == 1


def test_double_claim_returns_none(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    first = claim_job(qdir, job["id"])
    second = claim_job(qdir, job["id"])
    assert first is not None
    assert second is None  # already claimed -> no double start


# --------------------------------------------------------------------------
# cancel
# --------------------------------------------------------------------------
def test_cancel_deletes_geplant(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    assert cancel_job(qdir, job["id"]) is True
    assert list(qdir.glob("*.json")) == []


def test_cancel_refuses_laufend(qdir):
    job = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    claim_job(qdir, job["id"])
    assert cancel_job(qdir, job["id"]) is False
    assert len(list(qdir.glob("*.laufend.json"))) == 1  # still there


# --------------------------------------------------------------------------
# list + corrupt handling
# --------------------------------------------------------------------------
def test_list_jobs_returns_all_states(qdir):
    a = enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    b = enqueue_job(qdir, mode="stock_data_daily", run_at=_now(), created_by="x")
    claim_job(qdir, b["id"])
    jobs = list_jobs(qdir)
    statuses = sorted(j["status"] for j in jobs)
    assert statuses == ["geplant", "laufend"]


def test_corrupt_file_is_skipped_not_raised(qdir):
    enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    # Dateiname colon-frei (wie _job_path sie erzeugt) → auch auf Windows anlegbar.
    (qdir / "2026-07-24T00-00-00Z__broken__deadbeef.geplant.json").write_text("{ not json", encoding="utf-8")
    # list + due must not raise
    jobs = list_jobs(qdir)
    due = due_jobs(qdir, now=_now())
    assert len(jobs) == 1
    assert len(due) == 1
    # corrupt file quarantined
    assert (qdir / "_corrupt").exists()


def test_destructive_modes_are_defined():
    assert "all" in DESTRUCTIVE_MODES
    assert "historical_full" in DESTRUCTIVE_MODES
    assert "only_run_migrations" in DESTRUCTIVE_MODES
    assert "option_data" not in DESTRUCTIVE_MODES


# --------------------------------------------------------------------------
# run_dispatch orchestrator (subprocess gemockt)
# --------------------------------------------------------------------------
def test_run_dispatch_starts_due_job_and_clears_queue(qdir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.job_dispatcher.subprocess.Popen",
        lambda cmd, **kw: calls.append(cmd),
    )
    enqueue_job(qdir, mode="option_data", run_at=_now() - timedelta(minutes=1), created_by="x")
    started = run_dispatch(qdir, now=_now())
    assert started == 1
    assert calls == [["/bin/bash", "/app/Skuld/run_data_collection.sh", "option_data"]]
    # laufend-Datei nach Start wieder entfernt (Job trackt sich via _status/)
    assert list(qdir.glob("*.laufend.json")) == []
    assert list(qdir.glob("*.geplant.json")) == []


def test_run_dispatch_skips_future_jobs(qdir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.job_dispatcher.subprocess.Popen",
        lambda cmd, **kw: calls.append(cmd),
    )
    enqueue_job(qdir, mode="option_data", run_at=_now() + timedelta(hours=1), created_by="x")
    assert run_dispatch(qdir, now=_now()) == 0
    assert calls == []
    assert len(list(qdir.glob("*.geplant.json"))) == 1  # bleibt geplant


def test_run_dispatch_rolls_back_on_start_failure(qdir, monkeypatch):
    def boom(cmd, **kw):
        raise OSError("bash not found")
    monkeypatch.setattr("src.job_dispatcher.subprocess.Popen", boom)
    enqueue_job(qdir, mode="option_data", run_at=_now(), created_by="x")
    assert run_dispatch(qdir, now=_now()) == 0
    # Claim zurückgerollt: wieder geplant, damit erneut versucht wird
    assert len(list(qdir.glob("*.geplant.json"))) == 1
    assert list(qdir.glob("*.laufend.json")) == []
