"""Non-blocking primitives for driving verification jobs.

Four steps, each a plain function over plain values::

    planned = plan(jobs, root)          # materialize inputs, detect reuse
    handles = submit(planned, runner)   # returns at once, nothing waits
    ready   = collect(handles, runner)  # only terminal jobs yield artifacts
    report  = analyze(ready, analyzer)  # caller supplies the physics

Nothing here sleeps or loops until completion: a caller that wants to wait
decides its own cadence and calls :func:`poll` again.  Jobs whose inputs are
unchanged and already succeeded are skipped rather than resubmitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from dft_utils.verify.ports import (
    Artifacts,
    JobHandle,
    JobState,
    JobStatus,
    VerificationRunner,
    VerifyJob,
)
from dft_utils.verify.workspace import (
    fingerprint,
    is_fresh,
    prepare_workspace,
    read_manifest,
)


@dataclass
class PlannedJob:
    """A job with its workspace prepared and its reuse status known."""

    job: VerifyJob
    workdir: Path
    fingerprint: str
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.job.label,
            "engine": self.job.engine.value,
            "workdir": str(self.workdir),
            "fingerprint": self.fingerprint,
            "cached": self.cached,
        }


@dataclass
class Report:
    """Outcome of :func:`analyze` over a set of collected jobs."""

    ok: bool
    results: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "results": self.results, "issues": self.issues}


# ── Steps ──────────────────────────────────────────────────────────────

def plan(
    jobs: Iterable[VerifyJob], root: Path, force: bool = False
) -> list[PlannedJob]:
    """Prepare a workspace per job and flag which ones can be reused."""
    root = Path(root)
    planned: list[PlannedJob] = []
    for job in jobs:
        cached = not force and is_fresh(root, job)
        workdir = prepare_workspace(root, job, force=force)
        planned.append(
            PlannedJob(
                job=job,
                workdir=workdir,
                fingerprint=fingerprint(job),
                cached=cached,
            )
        )
    return planned


def submit(
    planned: Sequence[PlannedJob], runner: VerificationRunner
) -> list[JobHandle]:
    """Submit every non-cached planned job.  Returns immediately."""
    handles: list[JobHandle] = []
    for item in planned:
        if item.cached:
            continue
        handles.append(runner.submit(item.job, item.workdir))
    return handles


def poll(
    handles: Sequence[JobHandle], runner: VerificationRunner
) -> list[JobStatus]:
    """Observe all handles once."""
    return [runner.poll(handle) for handle in handles]


def collect(
    handles: Sequence[JobHandle],
    runner: VerificationRunner,
    statuses: Sequence[JobStatus] | None = None,
) -> list[Artifacts]:
    """Collect artifacts for handles that have reached a terminal state.

    Pass ``statuses`` from an earlier :func:`poll` to avoid polling twice.
    """
    if statuses is None:
        statuses = poll(handles, runner)
    return [
        runner.collect(status.handle) for status in statuses if status.is_terminal
    ]


def collect_cached(planned: Sequence[PlannedJob]) -> list[Artifacts]:
    """Artifacts for jobs that were skipped because a fresh run exists."""
    out: list[Artifacts] = []
    for item in planned:
        if not item.cached:
            continue
        manifest = read_manifest(item.workdir)
        handle = JobHandle(
            job_id=manifest.job_id if manifest else "",
            backend=manifest.backend if manifest else "cache",
            label=item.job.label,
            workdir=item.workdir,
            fingerprint=item.fingerprint,
        )
        files = {
            p.name: p for p in sorted(item.workdir.iterdir()) if p.is_file()
        }
        out.append(
            Artifacts(
                handle=handle,
                state=JobState.SUCCEEDED,
                root=item.workdir,
                files=files,
                message="reused: inputs unchanged since last successful run",
            )
        )
    return out


def analyze(
    artifacts: Iterable[Artifacts],
    analyzer: Callable[[Artifacts], dict[str, Any]],
) -> Report:
    """Apply ``analyzer`` to each artifact set and aggregate the verdict.

    ``analyzer`` owns all physics; this only aggregates.  A result is a
    failure if the analyzer returns ``ok=False`` or the job did not succeed.
    """
    results: list[dict[str, Any]] = []
    issues: list[str] = []
    for art in artifacts:
        if art.state is not JobState.SUCCEEDED:
            issues.append(f"{art.handle.label}: job state {art.state.value}")
            results.append(
                {"label": art.handle.label, "ok": False, "state": art.state.value}
            )
            continue
        result = dict(analyzer(art))
        result.setdefault("label", art.handle.label)
        result.setdefault("ok", True)
        if not result["ok"]:
            issues.extend(
                result.get("issues") or [f"{art.handle.label}: analysis failed"]
            )
        results.append(result)
    return Report(ok=not issues, results=results, issues=issues)
