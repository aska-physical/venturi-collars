#!/usr/bin/env python3
"""Regression tests proving verify.py fails closed under python3 -O."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify


def _copy_repo(dst: Path) -> Path:
    work = dst / "repo"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return work


class VerifyOptimizedModeTests(unittest.TestCase):
    def test_clean_tree_passes_all_isolated_modes(self) -> None:
        for flags in (["-I", "-B"], ["-I", "-O", "-B"], ["-I", "-B", "-W", "error"], ["-I", "-O", "-B", "-W", "error"]):
            proc = subprocess.run(
                [sys.executable, *flags, "verify.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=f"flags={flags} stderr={proc.stderr}")
            self.assertIn("[PASS]", proc.stdout)
            self.assertIn("(8/8 controls): OK", proc.stdout)

    def test_clean_write_is_idempotent_and_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = _copy_repo(Path(td))
            cert_json = work / "results" / "certificate.json"
            original_cert_bytes = cert_json.read_bytes()

            proc_w = subprocess.run(
                [sys.executable, "-I", "-O", "-B", "-W", "error", "verify.py", "--write"],
                cwd=work,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc_w.returncode, 0, msg=proc_w.stderr)
            self.assertEqual(cert_json.read_bytes(), original_cert_bytes)

            tampered = json.loads(original_cert_bytes.decode("utf-8"))
            tampered["telemetry_power_margin_at_4ms_x"] = 999.0
            cert_json.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            proc_d = subprocess.run(
                [sys.executable, "-I", "-O", "-B", "verify.py"],
                cwd=work,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc_d.returncode, 1)
            self.assertIn("mismatch", proc_d.stderr)

    def test_low_power_and_first_law_tampering_fail_closed_under_standard_and_O_write(self) -> None:
        """Tampering k_em=0.05 (low power) or k_em=15.0 (First-Law violation >20%) must fail closed."""
        cases = [
            ("low_power_k_em_0.05", r"\bk_em\s*=\s*1\.85\b", "k_em = 0.05", "hybrid harvested power"),
            ("first_law_k_em_15.0", r"\bk_em\s*=\s*1\.85\b", "k_em = 15.0", "exceeds 20% of fluid loss"),
        ]
        for label, pattern, repl, expected_msg in cases:
            for mode in ([], ["-O"]):
                with self.subTest(case=label, mode=mode), tempfile.TemporaryDirectory() as td:
                    work = _copy_repo(Path(td))
                    verify_py = work / "verify.py"
                    cert_json = work / "results" / "certificate.json"
                    original_cert_bytes = cert_json.read_bytes()

                    src = verify_py.read_text(encoding="utf-8")
                    patched, n_sub = re.subn(pattern, repl, src, count=1)
                    self.assertEqual(n_sub, 1, msg=f"pattern {pattern!r} not found")
                    verify_py.write_text(patched, encoding="utf-8")

                    for extra_args in ([], ["--write"], []):
                        proc = subprocess.run(
                            [sys.executable, "-I", *mode, "-B", "verify.py", *extra_args],
                            cwd=work,
                            text=True,
                            capture_output=True,
                            check=False,
                        )
                        self.assertNotEqual(
                            proc.returncode,
                            0,
                            msg=f"case={label} mode={mode} args={extra_args} unexpectedly passed: {proc.stdout}",
                        )
                        self.assertIn("CheckFailure", proc.stderr)
                        self.assertIn(expected_msg, proc.stderr)

                    self.assertEqual(cert_json.read_bytes(), original_cert_bytes)

    def test_all_guards_and_strict_boundaries_fail_closed_in_process(self) -> None:
        """Exercise every require() guard and exact strict-inequality boundary directly."""
        with self.assertRaises(verify.CheckFailure):
            verify.require(False, "direct require failure")

        # Hybrid 1.8 m/s power floor: exact boundary == 0.08 mW must fail strict '>'
        orig_eval = verify.evaluate_venturi_collar
        def _low_hybrid_boundary(d, b, ang, u, hybrid_em_coil=True, num_reeds=6):
            res = orig_eval(d, b, ang, u, hybrid_em_coil=hybrid_em_coil, num_reeds=num_reeds)
            if hybrid_em_coil and u == 1.8:
                res["P_total_harvested_mW"] = 0.08
            return res

        with mock.patch.object(verify, "evaluate_venturi_collar", side_effect=_low_hybrid_boundary):
            with self.assertRaises(verify.CheckFailure) as ctx:
                verify.run_verification()
            self.assertIn("hybrid harvested power", str(ctx.exception))

        # Piezo-only 4.0 m/s ceiling: exact boundary == 0.08 mW must fail strict '<'
        def _piezo_boundary(d, b, ang, u, hybrid_em_coil=True, num_reeds=6):
            res = orig_eval(d, b, ang, u, hybrid_em_coil=hybrid_em_coil, num_reeds=num_reeds)
            if not hybrid_em_coil and u == 4.0:
                res["P_total_harvested_mW"] = 0.08
            return res

        with mock.patch.object(verify, "evaluate_venturi_collar", side_effect=_piezo_boundary):
            with self.assertRaises(verify.CheckFailure) as ctx:
                verify.run_verification()
            self.assertIn("piezo-only harvested power", str(ctx.exception))

        # Pressure drop ceiling at 4.0 m/s: exact boundary == 6.0 Pa must fail strict '<'
        def _dp_boundary(d, b, ang, u, hybrid_em_coil=True, num_reeds=6):
            res = orig_eval(d, b, ang, u, hybrid_em_coil=hybrid_em_coil, num_reeds=num_reeds)
            if hybrid_em_coil and ang == 7.0 and u == 4.0:
                res["dP_total_Pa"] = 6.0
            return res

        with mock.patch.object(verify, "evaluate_venturi_collar", side_effect=_dp_boundary):
            with self.assertRaises(verify.CheckFailure) as ctx:
                verify.run_verification()
            self.assertIn("total pressure drop", str(ctx.exception))

        # Must-fail controls guard: failing any control (e.g. reed strain >= 0.25%) must fail closed
        def _strain_control_fail(d, b, ang, u, hybrid_em_coil=True, num_reeds=6):
            res = orig_eval(d, b, ang, u, hybrid_em_coil=hybrid_em_coil, num_reeds=num_reeds)
            if hybrid_em_coil and u == 6.0:
                res["peak_cfrp_strain_pct"] = 0.30
            return res

        with mock.patch.object(verify, "evaluate_venturi_collar", side_effect=_strain_control_fail):
            with self.assertRaises(verify.CheckFailure) as ctx:
                verify.run_verification()
            self.assertIn("reed_exceeds_m55j_0.8pct_ultimate_strain_at_6ms", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
