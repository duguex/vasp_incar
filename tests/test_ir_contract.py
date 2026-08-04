"""Contract tests for the shared SemanticIR.

Guards the architecture invariant that the canonical IR lives in the neutral
``dft_utils.ir`` layer: the ``omx_tools.semantic.ir`` shim and the package
re-export must forward the *same* objects, and the envelope round-trip must be
loss-free (a goal of the semantic round-trip design).
"""

import pytest

import dft_utils.ir as neutral_ir
import omx_tools.semantic.ir as backend_shim
from dft_utils.ir import SemanticIR
from omx_tools.semantic import SemanticIR as PkgIR


class TestSingleSourceOfTruth:
    """The IR must not be duplicated across layers."""

    def test_backend_shim_forwards_same_objects(self):
        for name in ("SemanticIR", "IR_SCHEMA", "IR_VERSION", "Smearing",
                     "TEMPLATE_TO_CLASS", "CLASS_TO_TEMPLATE",
                     "ismear_to_method", "xc_to_gga"):
            assert getattr(backend_shim, name) is getattr(neutral_ir, name), name

    def test_package_reexport_is_the_neutral_ir(self):
        assert PkgIR is neutral_ir.SemanticIR
        assert SemanticIR is neutral_ir.SemanticIR


class TestEnvelopeRoundTrip:
    """to_envelope / from_envelope must be an identity round-trip."""

    def _sample(self) -> SemanticIR:
        return SemanticIR(
            calc_class="scf",
            structure_ref="Si:2",
            physics={"xc": "PBE", "cutoff_eV": 520.0, "smearing": {"method": "mp"}},
            ionic={"motion": "ions", "max_steps": 60},
            provenance={"source_code": "vasp", "unmapped": ["FOO"]},
            code_native={"vasp": {"ENCUT": "520"}},
        )

    def test_envelope_round_trip_identity(self):
        ir = self._sample()
        payload = SemanticIR.from_envelope(ir.to_envelope())
        dumped = payload.model_dump()
        assert dumped == ir.model_dump()

    def test_envelope_carries_version(self):
        env = self._sample().to_envelope()
        assert env["_version"] == neutral_ir.IR_VERSION
        assert env["data"]["version"] == neutral_ir.IR_VERSION


class TestSchemaStability:
    """A version bump without a migration note must be a deliberate change.

    We pin the current schema name + model field set so an unintended schema
    drift is caught here rather than silently in producers/consumers.
    """

    def test_schema_and_version_pinned(self):
        assert neutral_ir.IR_SCHEMA == "dft_semantic_ir"
        assert neutral_ir.IR_VERSION == "0.3.0"

    def test_top_level_fields_stable(self):
        fields = set(SemanticIR.model_fields)
        assert fields == {
            "schema_name", "version", "calc_class", "structure_ref",
            "physics", "ionic", "electronics_algo", "code_native",
            "provenance", "ase_params", "openmx_template",
        }