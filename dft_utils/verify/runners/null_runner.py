"""Backend that accepts jobs and runs nothing.

Used for dry runs, for tests, and as the fallback when no real backend is
configured — plan/submit/collect logic can be exercised end to end without an
engine, a container, or CRISP.

Jobs go straight to a terminal state chosen at construction time
(``succeeded`` by default), so polling loops terminate.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from dft_utils.verify.ports import (
    Artifacts,
    JobHandle,
    JobState,
    JobStatus,
    VerifyJob,
)
from dft_utils.verify.workspace import fingerprint, update_manifest

_counter = itertools.count(1)


class NullRunner:
    """No-op :class:`~dft_utils.verify.ports.VerificationRunner`."""

    name = "null"

    def __init__(self, final_state: JobState = JobState.SUCCEEDED) -> None:
        self.final_state = final_state
        self.submitted: dict[str, JobHandle] = {}

    def available(self) -> bool:
        return True

    def submit(self, job: VerifyJob, workdir: Path) -> JobHandle:
        handle = JobHandle(
            job_id=f"null-{next(_counter)}",
            backend=self.name,
            label=job.label,
            workdir=Path(workdir),
            fingerprint=fingerprint(job),
        )
        self.submitted[handle.job_id] = handle
        update_manifest(
            workdir, backend=self.name, job_id=handle.job_id, state="submitted"
        )
        return handle

    def poll(self, handle: JobHandle) -> JobStatus:
        return JobStatus(
            handle=handle,
            state=self.final_state,
            message="null backend: no engine was run",
        )

    def collect(self, handle: JobHandle) -> Artifacts:
        root = Path(handle.workdir)
        files = (
            {p.name: p for p in sorted(root.iterdir()) if p.is_file()}
            if root.is_dir()
            else {}
        )
        update_manifest(root, state=self.final_state.value)
        return Artifacts(
            handle=handle,
            state=self.final_state,
            root=root,
            files=files,
            message="null backend: inputs only, no engine output",
        )

    def cancel(self, handle: JobHandle) -> bool:
        return self.submitted.pop(handle.job_id, None) is not None
