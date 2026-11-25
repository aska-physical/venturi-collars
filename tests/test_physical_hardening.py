#!/usr/bin/env python3
"""Zero-bare-assert R5 physical hardening regression tests for aska-physical/venturi-collars (v1.1.0).

Verifies:
  1. Pure dimensionless supercritical Hopf amplitude scaling (deleted v1.0.0's unexplained '+ 6.0' m^2/s^2
     denominator constant), restoring 1.8 m/s tip amplitude (1.341 -> 1.991 mm) and power (0.104 -> 0.229 mW).
  2. Continuous Gibson/Idelchik + Kline-Reneau (2*theta, AR=1/beta) conical diffuser stall loss model
     with smooth sharp-baffle vena-contracta onset (zero 8 deg or 15 deg step cliffs; interior friction/stall
     optimum near 4 deg; strict K increase with both 2*theta past optimum and area ratio AR=1/beta).
  3. Fail-closed incompressible throat Mach validity gate (Ma_throat <= 0.30, rejecting tight beta or high U).
  4. Zero bare assert statements across verify.py and this test file.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify


class TestVenturiCollarsPhysicalHardening(unittest.TestCase):
    def test_zero_bare_asserts_in_verify_and_tests(self) -> None:
        for rel in ("verify.py", "tests/test_physical_hardening.py", "tests/test_verify_O_safety.py", "tests/test_verify_nan_zoneb.py"):
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            self.assertEqual([n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)], [], f"bare assert in {rel}")

    def test_supercritical_hopf_amplitude_deletes_naked_plus6(self) -> None:
        # Clean dimensionless Hopf factor at 1.8 m/s turndown vs legacy U_sat = sqrt(6)
        r_clean = verify.evaluate_venturi_collar(0.20, 0.64, 7.0, 1.8, hybrid_em_coil=True)
        r_legacy = verify.evaluate_venturi_collar(0.20, 0.64, 7.0, 1.8, hybrid_em_coil=True, U_sat_m_s=math.sqrt(6.0))

        self.assertAlmostEqual(r_clean["tip_amp_mm"], 1.991, places=3)
        self.assertAlmostEqual(r_legacy["tip_amp_mm"], 1.341, places=3)
        self.assertAlmostEqual(r_clean["P_total_harvested_mW"], 0.2291, places=3)
        self.assertAlmostEqual(r_legacy["P_total_harvested_mW"], 0.1040, places=3)

        # Power scales strictly as amplitude squared: (1.341 / 1.991)^2 ~= 0.4538
        amp_sq_ratio = (r_legacy["tip_amp_mm"] / r_clean["tip_amp_mm"]) ** 2
        pwr_ratio = r_legacy["P_total_harvested_mW"] / r_clean["P_total_harvested_mW"]
        self.assertAlmostEqual(pwr_ratio, amp_sq_ratio, delta=0.002)
        self.assertLess(pwr_ratio, 0.46)

        # Dimensional invariance check: doubling both U_t, U_c, and U_sat leaves vel_factor invariant
        vf1 = verify.supercritical_vel_factor(3.0, 2.0, U_sat_m_s=1.5)
        vf2 = verify.supercritical_vel_factor(6.0, 4.0, U_sat_m_s=3.0)
        self.assertAlmostEqual(vf1, vf2, places=12)

        # Sub-critical throat speed returns exactly 0.0
        self.assertEqual(verify.supercritical_vel_factor(2.0, 2.23), 0.0)
        self.assertEqual(verify.supercritical_vel_factor(2.23, 2.23), 0.0)

    def test_diffuser_stall_is_continuous_and_depends_on_angle_and_area_ratio(self) -> None:
        # 1. Straight duct beta=1.0 gives exact zero minor loss even at theta=0.0
        k_straight, stall_straight = verify.compute_venturi_loss_coeff(1.0, 0.0)
        self.assertEqual(k_straight, 0.0)
        self.assertEqual(stall_straight, 0.0)

        # 2. C0 continuity across former 8 deg cliff AND 15 deg vena-contracta transition AND 45..90 deg
        for boundary in (8.0, 15.0, 45.0):
            k_lo, _ = verify.compute_venturi_loss_coeff(0.64, boundary)
            k_hi, _ = verify.compute_venturi_loss_coeff(0.64, boundary + 0.01)
            self.assertLess(abs(k_hi - k_lo), 0.002, msg=f"discontinuity detected near {boundary} deg: {k_lo} -> {k_hi}")

        # 90 deg flat orifice plate does not overflow tan(pi/2)
        k_90, s_90 = verify.compute_venturi_loss_coeff(0.64, 90.0)
        self.assertTrue(math.isfinite(k_90) and k_90 > 2.0)
        self.assertEqual(s_90, 1.0)

        # 3. Physical interior friction-vs-stall optimum near 4 deg, then strictly increasing with stall
        k_1, _ = verify.compute_venturi_loss_coeff(0.64, 1.0)
        k_4, _ = verify.compute_venturi_loss_coeff(0.64, 4.0)
        k_7, _ = verify.compute_venturi_loss_coeff(0.64, 7.0)
        k_10, _ = verify.compute_venturi_loss_coeff(0.64, 10.0)
        k_15, _ = verify.compute_venturi_loss_coeff(0.64, 15.0)
        k_25, _ = verify.compute_venturi_loss_coeff(0.64, 25.0)
        k_45, _ = verify.compute_venturi_loss_coeff(0.64, 45.0)
        self.assertGreater(k_1, k_4)
        self.assertLess(k_4, k_7)
        self.assertLess(k_7, k_10)
        self.assertLess(k_10, k_15)
        self.assertLess(k_15, k_25)
        self.assertLess(k_25, k_45)

        # 4. Kline-Reneau area-ratio stall intensification: at 10 deg, higher AR (smaller beta) has higher stall factor
        _, stall_b80 = verify.compute_venturi_loss_coeff(0.80, 10.0)
        _, stall_b64 = verify.compute_venturi_loss_coeff(0.64, 10.0)
        _, stall_b50 = verify.compute_venturi_loss_coeff(0.50, 10.0)
        _, stall_b35 = verify.compute_venturi_loss_coeff(0.35, 10.0)
        self.assertLess(stall_b80, stall_b64)
        self.assertLess(stall_b64, stall_b50)
        self.assertLess(stall_b50, stall_b35)

    def test_incompressible_mach_gate_and_angle_bounds_fail_closed(self) -> None:
        # Tight contraction beta=0.05 at 6.0 m/s -> U_throat = 120 m/s, Ma = 0.350 > 0.30 -> rejected!
        with self.assertRaises(verify.CheckFailure) as ctx1:
            verify.evaluate_venturi_collar(0.20, 0.05, 7.0, 6.0, hybrid_em_coil=True)
        self.assertIn("Mach", str(ctx1.exception))

        # Supersonic throat beta=0.01 at 6.0 m/s -> U_throat = 600 m/s, Ma = 1.75 -> rejected!
        with self.assertRaises(verify.CheckFailure) as ctx2:
            verify.evaluate_venturi_collar(0.20, 0.01, 7.0, 6.0, hybrid_em_coil=True)
        self.assertIn("Mach", str(ctx2.exception))

        # High duct speed crossing exact Ma = 0.30 boundary
        u_just_below = 0.299 * verify.A_SOUND_M_S * 0.64
        u_just_above = 0.301 * verify.A_SOUND_M_S * 0.64
        r_ok = verify.evaluate_venturi_collar(0.20, 0.64, 7.0, u_just_below, hybrid_em_coil=True)
        self.assertLess(r_ok["Ma_throat"], 0.30)
        with self.assertRaises(verify.CheckFailure) as ctx3:
            verify.evaluate_venturi_collar(0.20, 0.64, 7.0, u_just_above, hybrid_em_coil=True)
        self.assertIn("Mach", str(ctx3.exception))

        # Invalid angles and saturation speed fail closed
        for bad_call in (
            (0.20, 0.64, 0.0, 4.0, True, 6, 0.0),      # beta < 1 with 0 deg diffuser cannot expand in finite length
            (0.20, 0.64, 90.1, 4.0, True, 6, 0.0),     # > 90 deg diffuser half-angle
            (0.20, 0.64, 7.0, 4.0, True, 6, -1.0),     # negative U_sat
            (0.20, 0.64, 7.0, 4.0, True, 6, float("nan")),
            (0.20, 0.64, 7.0, 4.0, True, 6, float("inf")),
        ):
            with self.assertRaises(verify.CheckFailure):
                verify.evaluate_venturi_collar(*bad_call)

    def test_certificate_controls_and_diagnostics_are_consistent(self) -> None:
        cert = verify.run_verification()
        self.assertEqual(cert["certificate_version"], "1.1.0")
        self.assertEqual(len(cert["must_fail_controls"]), 8)
        self.assertTrue(all(c["rejected"] for c in cert["must_fail_controls"]))
        diag = cert["physical_hardening_diagnostics"]
        self.assertLess(diag["turndown_1p8ms_legacy_plus6_power_ratio"], 0.46)
        self.assertLess(diag["diffuser_loss_4deg_opt_K"], diag["diffuser_loss_7deg_design_K"])
        self.assertLess(diag["diffuser_loss_7deg_design_K"], diag["diffuser_loss_15deg_stall_K"])
        self.assertLess(diag["diffuser_loss_15deg_stall_K"], diag["diffuser_loss_25deg_stall_K"])


if __name__ == "__main__":
    unittest.main()
