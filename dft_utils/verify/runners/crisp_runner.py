"""Backend that delegates engine execution to CRISP.

CRISP (``~/crisp``) owns scheduling, containers, and mpirun.  This module is
the only place in the repo that knows CRISP exists, and it talks to exactly
one thing: the top-level ``crisp_api`` facade.  CRISP's ``shared``, ``daemon``,
``cli`` and ``webui`` packages are internals and must never be imported here —
if a needed capability is missing from the facade, extend the facade in CRISP
rather than reaching past it.

Expected facade surface (each resolved by name with aliases, so CRISP can
name things its own way)::

    submit(spec: dict) -> str | dict        # id, or dict with id/job_id
    status(job_id: str) -> str | dict       # state token, or dict with state
    artifacts(job_id: str) -> str | dict    # root path, or dict of files
    cancel(job_id: str) -> bool             # optional

Every call must return promptly; this runner never waits for a calculation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from dft_utils.verify.ports import (
    Artifacts,
    JobHandle,
    JobState,
    JobStatus,
    RunnerError,
    RunnerUnavailable,
    VerifyJob,
    parse_state,
)
from dft_utils.verify.workspace import fingerprint, update_manifest

# facade function → accepted names, in priority order
_ENTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "submit": ("submit", "submit_job", "submit_calculation"),
    "status": ("status", "job_status", "get_status", "poll"),
    "artifacts": ("artifacts", "job_artifacts", "get_artifacts", "results"),
    "cancel": ("cancel", "cancel_job", "kill"),
}

_ID_KEYS = ("job_id", "id", "jobid", "uuid")
_STATE_KEYS = ("state", "status", "job_state")
_MESSAGE_KEYS = ("message", "detail", "error", "reason")
_EXIT_KEYS = ("exit_code", "returncode", "rc")
_ROOT_KEYS = ("root", "workdir", "dir", "path", "output_dir")


def _import_facade() -> Any:
    try:
        import crisp_api  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RunnerUnavailable(
            "crisp_api is not importable; install/expose the CRISP facade "
            "(only the crisp_api module is a supported dependency)"
        ) from exc
    return crisp_api


def _resolve(facade: Any, kind: str) -> Callable[..., Any] | None:
    for name in _ENTRY_ALIASES[kind]:
        fn = getattr(facade, name, None)
        if callable(fn):
            return fn
    return None


def _first(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


class CrispRunner:
    """Asynchronous :class:`~dft_utils.verify.ports.VerificationRunner`
    backed by the ``crisp_api`` facade."""

    name = "crisp"

    def __init__(self, facade: Any = None) -> None:
        """``facade`` may be injected (tests, alternative deployments);
        otherwise ``crisp_api`` is imported lazily on first use."""
        self._facade = facade

    # ── facade access ──────────────────────────────────────────────

    @property
    def facade(self) -> Any:
        if self._facade is None:
            self._facade = _import_facade()
        return self._facade

    def _entry(self, kind: str) -> Callable[..., Any]:
        fn = _resolve(self.facade, kind)
        if fn is None:
            raise RunnerUnavailable(
                f"crisp_api exposes no {kind}() "
                f"(tried: {', '.join(_ENTRY_ALIASES[kind])})"
            )
        return fn

    def available(self) -> bool:
        try:
            facade = self.facade
        except RunnerUnavailable:
            return False
        return all(_resolve(facade, k) is not None for k in ("submit", "status"))

    # ── runner protocol ────────────────────────────────────────────

    def submit(self, job: VerifyJob, workdir: Path) -> JobHandle:
        workdir = Path(workdir)
        fp = fingerprint(job)
        spec: dict[str, Any] = {
            "engine": job.engine.value,
            "workdir": str(workdir),
            "inputs": sorted({**job.inputs, **job.input_files}),
            "label": job.label,
            "fingerprint": fp,
            **job.resources.to_dict(),
            "extra": dict(job.metadata),
        }
        try:
            raw = self._entry("submit")(spec)
        except RunnerUnavailable:
            raise
        except Exception as exc:
            raise RunnerError(f"crisp_api submit failed for {job.label}: {exc}") from exc

        job_id = _first(raw, _ID_KEYS) if isinstance(raw, dict) else raw
        if not job_id:
            raise RunnerError(f"crisp_api submit returned no job id: {raw!r}")

        handle = JobHandle(
            job_id=str(job_id),
            backend=self.name,
            label=job.label,
            workdir=workdir,
            fingerprint=fp,
            submitted_at=time.time(),
            backend_ref=raw if isinstance(raw, dict) else None,
        )
        update_manifest(
            workdir, backend=self.name, job_id=handle.job_id, state="submitted"
        )
        return handle

    def poll(self, handle: JobHandle) -> JobStatus:
        try:
            raw = self._entry("status")(handle.job_id)
        except RunnerUnavailable:
            raise
        except Exception as exc:
            raise RunnerError(
                f"crisp_api status failed for {handle.job_id}: {exc}"
            ) from exc

        if isinstance(raw, dict):
            state = parse_state(_first(raw, _STATE_KEYS))
            message = str(_first(raw, _MESSAGE_KEYS) or "")
            exit_code = _first(raw, _EXIT_KEYS)
        else:
            state, message, exit_code = parse_state(raw), "", None

        status = JobStatus(
            handle=handle,
            state=state,
            message=message,
            exit_code=int(exit_code) if exit_code is not None else None,
        )
        update_manifest(handle.workdir, state=state.value)
        return status

    def collect(self, handle: JobHandle) -> Artifacts:
        state = self.poll(handle).state
        root = Path(handle.workdir)
        files: dict[str, Path] = {}
        message = ""

        entry = _resolve(self.facade, "artifacts")
        if entry is not None:
            try:
                raw = entry(handle.job_id)
            except Exception as exc:
                raise RunnerError(
                    f"crisp_api artifacts failed for {handle.job_id}: {exc}"
                ) from exc
            if isinstance(raw, dict):
                reported_root = _first(raw, _ROOT_KEYS)
                if reported_root:
                    root = Path(reported_root)
                message = str(_first(raw, _MESSAGE_KEYS) or "")
                for name, path in (raw.get("files") or {}).items():
                    files[str(name)] = Path(path)
            elif raw:
                root = Path(raw)

        if not files and root.is_dir():
            files = {p.name: p for p in sorted(root.iterdir()) if p.is_file()}

        return Artifacts(
            handle=handle, state=state, root=root, files=files, message=message
        )

    def cancel(self, handle: JobHandle) -> bool:
        entry = _resolve(self.facade, "cancel")
        if entry is None:
            return False
        try:
            return bool(entry(handle.job_id))
        except Exception as exc:
            raise RunnerError(
                f"crisp_api cancel failed for {handle.job_id}: {exc}"
            ) from exc
