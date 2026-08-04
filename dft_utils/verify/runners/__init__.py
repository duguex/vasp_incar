"""Verification backends.

``crisp`` delegates real engine runs to CRISP; ``null`` runs nothing and is
used for dry runs and tests.  Backends are imported lazily so that a missing
``crisp_api`` never breaks importing ``dft_utils``.
"""

from __future__ import annotations

from dft_utils.verify.ports import RunnerUnavailable, VerificationRunner

_BACKENDS = ("crisp", "null")


def get_runner(name: str = "crisp", **kwargs) -> VerificationRunner:
    """Instantiate a backend by name.

    Raises :class:`RunnerUnavailable` for unknown names, so callers can treat
    "no such backend" and "backend not usable here" the same way.
    """
    key = name.strip().lower()
    if key == "null":
        from dft_utils.verify.runners.null_runner import NullRunner

        return NullRunner(**kwargs)
    if key == "crisp":
        from dft_utils.verify.runners.crisp_runner import CrispRunner

        return CrispRunner(**kwargs)
    raise RunnerUnavailable(
        f"unknown verification backend {name!r} (known: {', '.join(_BACKENDS)})"
    )


def list_backends() -> tuple[str, ...]:
    return _BACKENDS


__all__ = ["get_runner", "list_backends"]
