"""Verification seam: value types and the runner port.

``dft_utils.verify`` defines *what* a verification job is and *how* results
come back.  It never executes an engine itself: execution is delegated to a
backend that implements :class:`VerificationRunner`.

The contract is deliberately asynchronous — ``submit`` returns immediately
with a :class:`JobHandle`, and progress is observed through ``poll``.  No
method may block until an engine run finishes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ── Errors ─────────────────────────────────────────────────────────────

class VerifyError(RuntimeError):
    """Base class for verification-seam failures."""


class RunnerUnavailable(VerifyError):
    """The backend cannot be used here (missing dependency, no daemon, ...)."""


class RunnerError(VerifyError):
    """The backend was reachable but the operation failed."""


# ── Enums ──────────────────────────────────────────────────────────────

class Engine(str, Enum):
    """DFT engine a job targets."""

    VASP = "vasp"
    OPENMX = "openmx"


class JobState(str, Enum):
    """Lifecycle state of a submitted job."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
)

# Synonyms seen in scheduler / backend vocabularies.
_STATE_ALIASES: dict[str, JobState] = {
    "queued": JobState.PENDING,
    "waiting": JobState.PENDING,
    "new": JobState.PENDING,
    "accepted": JobState.SUBMITTED,
    "started": JobState.RUNNING,
    "run": JobState.RUNNING,
    "active": JobState.RUNNING,
    "done": JobState.SUCCEEDED,
    "complete": JobState.SUCCEEDED,
    "completed": JobState.SUCCEEDED,
    "finished": JobState.SUCCEEDED,
    "success": JobState.SUCCEEDED,
    "ok": JobState.SUCCEEDED,
    "error": JobState.FAILED,
    "failure": JobState.FAILED,
    "aborted": JobState.FAILED,
    "timeout": JobState.FAILED,
    "canceled": JobState.CANCELLED,
    "killed": JobState.CANCELLED,
}


def parse_state(value: Any) -> JobState:
    """Normalize a backend state token onto :class:`JobState`.

    Unrecognized tokens become :attr:`JobState.UNKNOWN` rather than raising —
    a strange status string must not break a polling loop.
    """
    if isinstance(value, JobState):
        return value
    if not isinstance(value, str):
        return JobState.UNKNOWN
    token = value.strip().lower()
    try:
        return JobState(token)
    except ValueError:
        return _STATE_ALIASES.get(token, JobState.UNKNOWN)


# ── Value types ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Resources:
    """Requested compute resources.  All fields are hints for the backend."""

    nprocs: int = 1
    threads: int = 1
    walltime_s: int | None = None
    queue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nprocs": self.nprocs,
            "threads": self.threads,
            "walltime_s": self.walltime_s,
            "queue": self.queue,
        }


@dataclass(frozen=True)
class VerifyJob:
    """One engine run to be verified.

    Attributes
    ----------
    label:
        Stable, human-meaningful name (``"si8_scf_vasp"``).  Used for the
        workspace directory, so keep it filesystem-safe.
    engine:
        Which DFT code runs this job.
    inputs:
        Mapping of input filename → file content.  Content is written into
        the workspace by :func:`dft_utils.verify.workspace.prepare_workspace`
        and hashed into the job fingerprint.
    input_files:
        Mapping of input filename → source path, for inputs too large or too
        binary to inline (POTCAR, pseudopotentials).  Copied, then hashed.
    resources:
        Compute request.
    metadata:
        Free-form provenance (element, template, tolerance set, ...).  Not
        part of the fingerprint.
    """

    label: str
    engine: Engine
    inputs: dict[str, str] = field(default_factory=dict)
    input_files: dict[str, Path] = field(default_factory=dict)
    resources: Resources = field(default_factory=Resources)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "engine": self.engine.value,
            "inputs": sorted(self.inputs),
            "input_files": {k: str(v) for k, v in sorted(self.input_files.items())},
            "resources": self.resources.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class JobHandle:
    """Backend-issued receipt for a submitted job."""

    job_id: str
    backend: str
    label: str
    workdir: Path
    fingerprint: str = ""
    submitted_at: float = field(default_factory=time.time)
    backend_ref: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "backend": self.backend,
            "label": self.label,
            "workdir": str(self.workdir),
            "fingerprint": self.fingerprint,
            "submitted_at": self.submitted_at,
        }


@dataclass(frozen=True)
class JobStatus:
    """Point-in-time observation of a job."""

    handle: JobHandle
    state: JobState
    message: str = ""
    exit_code: int | None = None
    observed_at: float = field(default_factory=time.time)

    @property
    def is_terminal(self) -> bool:
        return self.state.is_terminal

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.handle.job_id,
            "label": self.handle.label,
            "state": self.state.value,
            "message": self.message,
            "exit_code": self.exit_code,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class Artifacts:
    """Files a finished job left behind."""

    handle: JobHandle
    state: JobState
    root: Path
    files: dict[str, Path] = field(default_factory=dict)
    message: str = ""

    def path(self, name: str) -> Path | None:
        return self.files.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.handle.job_id,
            "label": self.handle.label,
            "state": self.state.value,
            "root": str(self.root),
            "files": {k: str(v) for k, v in sorted(self.files.items())},
            "message": self.message,
        }


# ── Runner port ────────────────────────────────────────────────────────

@runtime_checkable
class VerificationRunner(Protocol):
    """Backend that executes :class:`VerifyJob` runs somewhere else.

    Implementations must be non-blocking: ``submit`` returns as soon as the
    job is accepted, and callers observe progress via ``poll``.
    """

    name: str

    def available(self) -> bool:
        """Whether this backend can currently accept work."""
        ...

    def submit(self, job: VerifyJob, workdir: Path) -> JobHandle:
        """Hand ``job`` to the backend and return immediately."""
        ...

    def poll(self, handle: JobHandle) -> JobStatus:
        """Observe the current state without waiting."""
        ...

    def collect(self, handle: JobHandle) -> Artifacts:
        """Gather output paths for a job that reached a terminal state."""
        ...

    def cancel(self, handle: JobHandle) -> bool:
        """Request cancellation.  Returns whether the backend accepted it."""
        ...
