"""Verification seam: ports, workspace, runners, drive primitives."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dft_utils.verify import (
    Artifacts,
    Engine,
    JobState,
    Resources,
    RunnerError,
    RunnerUnavailable,
    VerificationRunner,
    VerifyJob,
    analyze,
    collect,
    collect_cached,
    fingerprint,
    get_runner,
    is_fresh,
    plan,
    poll,
    prepare_workspace,
    read_manifest,
    submit,
)
from dft_utils.verify.ports import parse_state
from dft_utils.verify.runners.crisp_runner import CrispRunner
from dft_utils.verify.runners.null_runner import NullRunner


def make_job(label: str = "si8_scf", **overrides) -> VerifyJob:
    kwargs = dict(
        label=label,
        engine=Engine.VASP,
        inputs={"INCAR": "ENCUT = 520\n", "POSCAR": "Si8\n"},
        resources=Resources(nprocs=4),
        metadata={"element": "Si"},
    )
    kwargs.update(overrides)
    return VerifyJob(**kwargs)


# ── ports ──────────────────────────────────────────────────────────────

def test_state_parsing_and_terminality():
    assert parse_state("QUEUED") is JobState.PENDING
    assert parse_state("done") is JobState.SUCCEEDED
    assert parse_state("Running") is JobState.RUNNING
    assert parse_state("nonsense-token") is JobState.UNKNOWN
    assert parse_state(None) is JobState.UNKNOWN
    assert JobState.SUCCEEDED.is_terminal
    assert JobState.FAILED.is_terminal
    assert not JobState.RUNNING.is_terminal


def test_runners_satisfy_protocol():
    assert isinstance(NullRunner(), VerificationRunner)
    assert isinstance(CrispRunner(facade=object()), VerificationRunner)


# ── workspace ──────────────────────────────────────────────────────────

def test_fingerprint_tracks_inputs_not_resources():
    base = make_job()
    same = make_job(resources=Resources(nprocs=64), metadata={"element": "Ge"})
    changed = make_job(inputs={"INCAR": "ENCUT = 400\n", "POSCAR": "Si8\n"})
    assert fingerprint(base) == fingerprint(same)
    assert fingerprint(base) != fingerprint(changed)


def test_fingerprint_covers_copied_input_files(tmp_path):
    potcar = tmp_path / "POTCAR"
    potcar.write_text("PAW_PBE Si\n")
    job = make_job(input_files={"POTCAR": potcar})
    before = fingerprint(job)
    potcar.write_text("PAW_PBE Ge\n")
    assert fingerprint(job) != before


def test_prepare_workspace_writes_inputs_and_manifest(tmp_path):
    job = make_job()
    workdir = prepare_workspace(tmp_path, job)
    assert (workdir / "INCAR").read_text() == "ENCUT = 520\n"
    manifest = read_manifest(workdir)
    assert manifest.engine is Engine.VASP
    assert manifest.fingerprint == fingerprint(job)
    assert set(manifest.inputs) == {"INCAR", "POSCAR"}
    assert manifest.state == "pending"


def test_prepare_workspace_preserves_outputs_when_unchanged(tmp_path):
    job = make_job()
    workdir = prepare_workspace(tmp_path, job)
    (workdir / "OUTCAR").write_text("engine output\n")
    prepare_workspace(tmp_path, job)
    assert (workdir / "OUTCAR").is_file()


def test_prepare_workspace_rewrites_when_inputs_change(tmp_path):
    workdir = prepare_workspace(tmp_path, make_job())
    prepare_workspace(tmp_path, make_job(inputs={"INCAR": "ENCUT = 400\n"}))
    assert (workdir / "INCAR").read_text() == "ENCUT = 400\n"


def test_manifest_write_is_atomic(tmp_path):
    job = make_job()
    workdir = prepare_workspace(tmp_path, job)
    leftovers = [p.name for p in workdir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    json.loads((workdir / "manifest.json").read_text())


def test_is_fresh_requires_succeeded_state(tmp_path):
    job = make_job()
    prepare_workspace(tmp_path, job)
    assert not is_fresh(tmp_path, job)
    runner = NullRunner()
    handle = runner.submit(job, tmp_path / job.label)
    runner.collect(handle)
    assert is_fresh(tmp_path, job)
    assert not is_fresh(tmp_path, make_job(inputs={"INCAR": "ENCUT = 400\n"}))


# ── null runner + drive ────────────────────────────────────────────────

def test_drive_roundtrip_with_null_runner(tmp_path):
    jobs = [make_job("a"), make_job("b")]
    runner = get_runner("null")
    planned = plan(jobs, tmp_path)
    assert [p.cached for p in planned] == [False, False]

    handles = submit(planned, runner)
    assert len(handles) == 2
    assert all(h.backend == "null" for h in handles)
    assert read_manifest(planned[0].workdir).job_id == handles[0].job_id

    statuses = poll(handles, runner)
    assert all(s.is_terminal for s in statuses)

    artifacts = collect(handles, runner, statuses)
    assert len(artifacts) == 2
    assert "INCAR" in artifacts[0].files


def test_cached_jobs_are_not_resubmitted(tmp_path):
    job = make_job()
    runner = get_runner("null")
    first = plan([job], tmp_path)
    collect(submit(first, runner), runner)

    second = plan([job], tmp_path)
    assert second[0].cached is True
    assert submit(second, runner) == []
    reused = collect_cached(second)
    assert len(reused) == 1
    assert reused[0].state is JobState.SUCCEEDED


def test_force_replans_cached_job(tmp_path):
    job = make_job()
    runner = get_runner("null")
    collect(submit(plan([job], tmp_path), runner), runner)
    assert plan([job], tmp_path, force=True)[0].cached is False


def test_non_terminal_jobs_yield_no_artifacts(tmp_path):
    runner = NullRunner(final_state=JobState.RUNNING)
    handles = submit(plan([make_job()], tmp_path), runner)
    assert collect(handles, runner) == []


def test_analyze_aggregates_verdicts(tmp_path):
    runner = get_runner("null")
    artifacts = collect(submit(plan([make_job("a"), make_job("b")], tmp_path), runner), runner)

    ok_report = analyze(artifacts, lambda art: {"ok": True, "energy": -10.0})
    assert ok_report.ok is True
    assert len(ok_report.results) == 2

    bad_report = analyze(
        artifacts, lambda art: {"ok": False, "issues": [f"{art.handle.label}: gap off"]}
    )
    assert bad_report.ok is False
    assert len(bad_report.issues) == 2


def test_analyze_flags_failed_jobs(tmp_path):
    handle = NullRunner().submit(make_job(), prepare_workspace(tmp_path, make_job()))
    failed = Artifacts(handle=handle, state=JobState.FAILED, root=handle.workdir)
    report = analyze([failed], lambda art: pytest.fail("analyzer must be skipped"))
    assert report.ok is False
    assert "failed" in report.issues[0]


# ── crisp runner ───────────────────────────────────────────────────────

class FakeCrispApi:
    """Stand-in for the CRISP facade, dict-shaped returns."""

    def __init__(self, state="running"):
        self.state = state
        self.specs: list[dict] = []
        self.cancelled: list[str] = []

    def submit(self, spec):
        self.specs.append(spec)
        return {"job_id": f"crisp-{len(self.specs)}"}

    def status(self, job_id):
        return {"state": self.state, "message": "from fake", "exit_code": 0}

    def artifacts(self, job_id):
        return {"root": self.specs[0]["workdir"], "files": {}}

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


class BareCrispApi:
    """Facade variant returning bare scalars and using alias names."""

    def submit_job(self, spec):
        return "job-7"

    def job_status(self, job_id):
        return "COMPLETE"


def test_crisp_runner_unavailable_without_facade(monkeypatch):
    monkeypatch.setitem(sys.modules, "crisp_api", None)
    runner = CrispRunner()
    assert runner.available() is False
    with pytest.raises(RunnerUnavailable):
        runner.submit(make_job(), Path("/tmp"))


def test_crisp_runner_submits_and_polls(tmp_path):
    fake = FakeCrispApi()
    runner = CrispRunner(facade=fake)
    assert runner.available() is True

    job = make_job()
    workdir = prepare_workspace(tmp_path, job)
    handle = runner.submit(job, workdir)
    assert handle.job_id == "crisp-1"
    assert fake.specs[0]["engine"] == "vasp"
    assert fake.specs[0]["nprocs"] == 4
    assert fake.specs[0]["fingerprint"] == fingerprint(job)
    assert read_manifest(workdir).state == "submitted"

    status = runner.poll(handle)
    assert status.state is JobState.RUNNING
    assert not status.is_terminal
    assert read_manifest(workdir).state == "running"

    fake.state = "succeeded"
    artifacts = runner.collect(handle)
    assert artifacts.state is JobState.SUCCEEDED
    assert "INCAR" in artifacts.files
    assert runner.cancel(handle) is True


def test_crisp_runner_accepts_alias_names_and_scalars(tmp_path):
    runner = CrispRunner(facade=BareCrispApi())
    job = make_job()
    handle = runner.submit(job, prepare_workspace(tmp_path, job))
    assert handle.job_id == "job-7"
    assert runner.poll(handle).state is JobState.SUCCEEDED
    assert runner.cancel(handle) is False  # no cancel entry point


def test_crisp_runner_rejects_missing_entry_points(tmp_path):
    runner = CrispRunner(facade=object())
    assert runner.available() is False
    with pytest.raises(RunnerUnavailable, match="no submit"):
        runner.submit(make_job(), tmp_path)


def test_crisp_runner_wraps_backend_failures(tmp_path):
    class Boom:
        def submit(self, spec):
            raise ValueError("daemon down")

    with pytest.raises(RunnerError, match="daemon down"):
        CrispRunner(facade=Boom()).submit(make_job(), tmp_path)


def test_unknown_backend_name():
    with pytest.raises(RunnerUnavailable, match="unknown verification backend"):
        get_runner("slurm")
