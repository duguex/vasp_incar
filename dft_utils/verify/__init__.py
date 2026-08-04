"""Verification seam: define engine runs here, execute them elsewhere.

vasp_wiki knows what a correct calculation looks like; it does not run one.
This package holds the job/result vocabulary (:mod:`ports`), the on-disk
workspace and fingerprint rules (:mod:`workspace`), the non-blocking
plan/submit/collect/analyze primitives (:mod:`drive`), and the backends
(:mod:`runners`) that hand work to CRISP or to nothing at all.

Existing container-driving scripts under ``scripts/`` remain the local
compatibility path; they are unaffected by this package.
"""

from __future__ import annotations

from dft_utils.verify.drive import (  # noqa: F401
    PlannedJob,
    Report,
    analyze,
    collect,
    collect_cached,
    plan,
    poll,
    submit,
)
from dft_utils.verify.ports import (  # noqa: F401
    Artifacts,
    Engine,
    JobHandle,
    JobState,
    JobStatus,
    Resources,
    RunnerError,
    RunnerUnavailable,
    VerificationRunner,
    VerifyError,
    VerifyJob,
    parse_state,
)
from dft_utils.verify.runners import get_runner, list_backends  # noqa: F401
from dft_utils.verify.workspace import (  # noqa: F401
    Manifest,
    fingerprint,
    is_fresh,
    prepare_workspace,
    read_manifest,
    write_json_atomic,
)

__all__ = [
    "Artifacts",
    "Engine",
    "JobHandle",
    "JobState",
    "JobStatus",
    "Manifest",
    "PlannedJob",
    "Report",
    "Resources",
    "RunnerError",
    "RunnerUnavailable",
    "VerificationRunner",
    "VerifyError",
    "VerifyJob",
    "analyze",
    "collect",
    "collect_cached",
    "fingerprint",
    "get_runner",
    "is_fresh",
    "list_backends",
    "parse_state",
    "plan",
    "poll",
    "prepare_workspace",
    "read_manifest",
    "submit",
    "write_json_atomic",
]
