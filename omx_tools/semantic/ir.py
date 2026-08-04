"""Backward-compatible re-export of the canonical semantic IR.

The IR now lives in the neutral ``dft_utils.ir`` module (shared by VASP and
OpenMX). This file exists so all existing ``from omx_tools.semantic.ir import
...`` imports keep working during and after the migration. New code should
import from :mod:`dft_utils.ir` directly.
"""

from __future__ import annotations

from dft_utils.ir import (  # noqa: F401
    CalcClass,
    CLASS_TO_TEMPLATE,
    CodeNative,
    ElectronicsAlgo,
    Ionic,
    IonicMotion,
    IR_SCHEMA,
    IR_VERSION,
    Physics,
    Provenance,
    SemanticIR,
    Smearing,
    SpinKind,
    TEMPLATE_TO_CLASS,
    gga_to_xc,
    ibrion_to_motion,
    ismear_to_method,
    ispin_to_spin,
    method_to_ismear,
    spin_to_ispin,
    xc_to_gga,
)