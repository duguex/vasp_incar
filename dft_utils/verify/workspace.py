"""Workspace layout, input fingerprints, and atomic manifests.

A workspace is one directory per job::

    <root>/<label>/
        manifest.json     # provenance + fingerprint, written atomically
        INCAR, POSCAR ...  # job inputs
        ...                # engine outputs, written by the backend

The fingerprint covers the engine, the input filenames, and the input bytes.
It is what makes "has this exact calculation already been run?" answerable
without re-reading every file, and it is stable across machines.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dft_utils.verify.ports import Engine, VerifyJob

MANIFEST_NAME = "manifest.json"
FINGERPRINT_VERSION = 1


# ── Fingerprints ───────────────────────────────────────────────────────

def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """SHA-256 of text, encoded UTF-8."""
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's contents, streamed (POTCARs are large)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_digests(job: VerifyJob) -> dict[str, str]:
    """Per-input SHA-256 digests, inline content and copied files alike."""
    digests = {name: hash_text(text) for name, text in job.inputs.items()}
    for name, src in job.input_files.items():
        src = Path(src)
        if not src.is_file():
            raise FileNotFoundError(f"input file for {name!r} not found: {src}")
        digests[name] = hash_file(src)
    return digests


def fingerprint(job: VerifyJob) -> str:
    """Content fingerprint of a job: engine + input names + input bytes.

    Deliberately excludes ``resources`` and ``metadata`` — running the same
    inputs on more cores is the same calculation.
    """
    digests = input_digests(job)
    payload = json.dumps(
        {
            "v": FINGERPRINT_VERSION,
            "engine": job.engine.value,
            "inputs": dict(sorted(digests.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hash_text(payload)


# ── Atomic writes ──────────────────────────────────────────────────────

def write_atomic(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` via a temp file in the same directory.

    A crashed or concurrent run must never leave a half-written manifest that
    a later poll would parse as truth.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def write_json_atomic(path: Path, data: Any) -> Path:
    """Serialize ``data`` as pretty JSON and write it atomically."""
    return write_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


# ── Manifest ───────────────────────────────────────────────────────────

@dataclass
class Manifest:
    """Provenance record stored next to a job's inputs."""

    label: str
    engine: Engine
    fingerprint: str
    inputs: dict[str, str] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    backend: str = ""
    job_id: str = ""
    state: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": FINGERPRINT_VERSION,
            "label": self.label,
            "engine": self.engine.value,
            "fingerprint": self.fingerprint,
            "inputs": dict(sorted(self.inputs.items())),
            "resources": self.resources,
            "metadata": self.metadata,
            "backend": self.backend,
            "job_id": self.job_id,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            label=data["label"],
            engine=Engine(data["engine"]),
            fingerprint=data.get("fingerprint", ""),
            inputs=dict(data.get("inputs", {})),
            resources=dict(data.get("resources", {})),
            metadata=dict(data.get("metadata", {})),
            backend=data.get("backend", ""),
            job_id=data.get("job_id", ""),
            state=data.get("state", "pending"),
        )

    def save(self, workdir: Path) -> Path:
        return write_json_atomic(Path(workdir) / MANIFEST_NAME, self.to_dict())


def read_manifest(workdir: Path) -> Manifest | None:
    """Load a workspace manifest, or None if absent/corrupt."""
    path = Path(workdir) / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def update_manifest(workdir: Path, **fields: Any) -> Manifest | None:
    """Patch selected manifest fields in place, atomically."""
    manifest = read_manifest(workdir)
    if manifest is None:
        return None
    for key, value in fields.items():
        setattr(manifest, key, value)
    manifest.save(workdir)
    return manifest


# ── Workspace preparation ──────────────────────────────────────────────

def job_workdir(root: Path, job: VerifyJob) -> Path:
    """Directory a job's files live in."""
    return Path(root) / job.label


def prepare_workspace(root: Path, job: VerifyJob, force: bool = False) -> Path:
    """Materialize ``job``'s inputs under ``root`` and write its manifest.

    Returns the workspace directory.  If a manifest with the same fingerprint
    is already present and ``force`` is false, inputs are left untouched so
    that engine outputs from a previous run survive.
    """
    workdir = job_workdir(root, job)
    fp = fingerprint(job)

    existing = read_manifest(workdir)
    if existing is not None and existing.fingerprint == fp and not force:
        return workdir

    workdir.mkdir(parents=True, exist_ok=True)
    for name, text in job.inputs.items():
        write_atomic(workdir / name, text)
    for name, src in job.input_files.items():
        shutil.copyfile(Path(src), workdir / name)

    Manifest(
        label=job.label,
        engine=job.engine,
        fingerprint=fp,
        inputs=input_digests(job),
        resources=job.resources.to_dict(),
        metadata=dict(job.metadata),
    ).save(workdir)
    return workdir


def is_fresh(root: Path, job: VerifyJob) -> bool:
    """Whether ``root`` already holds a succeeded run of this exact job."""
    manifest = read_manifest(job_workdir(root, job))
    return (
        manifest is not None
        and manifest.fingerprint == fingerprint(job)
        and manifest.state == "succeeded"
    )
