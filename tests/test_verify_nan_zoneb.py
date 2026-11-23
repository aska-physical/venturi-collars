#!/usr/bin/env python3
"""
R5 + Zone-B + NaN-swallowing + -O safety regression suite for venturi-collars/verify.py.

Pure Python 3 stdlib. Zero bare assert statements (bit-identical across -I -B, -I -O -B, -I -B -W error).
"""
from __future__ import annotations

import contextlib
import io
import os
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

import verify  # noqa: E402


def _req(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _run_main_inproc(cert_path: Path, argv: list[str]) -> tuple[int, str, str]:
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with (
        mock.patch.object(verify, "CERT_PATH", cert_path),
        mock.patch.object(sys, "argv", ["verify.py", *argv]),
        contextlib.redirect_stdout(out_buf),
        contextlib.redirect_stderr(err_buf),
    ):
        rc = verify.main()
    return rc, out_buf.getvalue(), err_buf.getvalue()


class VenturiHardeningTests(unittest.TestCase):
    def test_01_three_mode_isolated_parity_and_idempotent_write(self) -> None:
        outputs: list[str] = []
        for flags in (["-I", "-B"], ["-I", "-O", "-B"], ["-I", "-B", "-W", "error"]):
            proc = subprocess.run(
                [sys.executable, *flags, "verify.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            _req(proc.returncode == 0, f"flags={flags} rc={proc.returncode} stderr={proc.stderr}")
            _req("(5/5 controls): OK" in proc.stdout, f"unexpected stdout: {proc.stdout!r}")
            outputs.append(proc.stdout)
        _req(outputs[0] == outputs[1] == outputs[2], "stdout differed across isolated R4 modes")

        orig = verify.CERT_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            cert_path = Path(td) / "results" / "certificate.json"
            rc, out, err = _run_main_inproc(cert_path, ["--write"])
            _req(rc == 0 and "(5/5 controls): OK" in out, f"--write failed: rc={rc} out={out} err={err}")
            _req(cert_path.read_bytes() == orig, "--write drifted from committed canonical bytes")
            # Re-writing over existing regular file stays idempotent
            rc2, _out2, err2 = _run_main_inproc(cert_path, ["--write"])
            _req(rc2 == 0 and cert_path.read_bytes() == orig, f"2nd --write failed: {rc2} {err2}")

    def test_02_nan_inf_and_invalid_domain_inputs_fail_closed(self) -> None:
        # Live S21c witness: U_duct_m_s=nan used to produce P_total_harvested_mW=0.9244 under -O!
        bad_calls = [
            ("U_duct_nan", (0.20, 0.64, 7.0, float("nan"), True, 6)),
            ("U_duct_inf", (0.20, 0.64, 7.0, float("inf"), True, 6)),
            ("U_duct_neg", (0.20, 0.64, 7.0, -1.0, True, 6)),
            ("U_duct_bool", (0.20, 0.64, 7.0, True, True, 6)),
            ("diam_zero", (0.0, 0.64, 7.0, 4.0, True, 6)),
            ("diam_nan", (float("nan"), 0.64, 7.0, 4.0, True, 6)),
            ("beta_zero", (0.20, 0.0, 7.0, 4.0, True, 6)),
            ("beta_above_1", (0.20, 1.05, 7.0, 4.0, True, 6)),
            ("angle_neg", (0.20, 0.64, -0.5, 4.0, True, 6)),
            ("hybrid_int", (0.20, 0.64, 7.0, 4.0, 1, 6)),
            ("reeds_zero", (0.20, 0.64, 7.0, 4.0, True, 0)),
            ("reeds_bool", (0.20, 0.64, 7.0, 4.0, True, True)),
        ]
        for label, args in bad_calls:
            try:
                verify.evaluate_venturi_collar(*args)
            except verify.CheckFailure:
                pass
            else:
                raise AssertionError(f"{label} was not rejected by evaluate_venturi_collar")

        # Direct strict_finite_min must never swallow NaN in either argument
        _req(verify.strict_finite_min(0.0040, 0.0010, "tip") == 0.0010, "strict_finite_min lower branch wrong")
        _req(verify.strict_finite_min(0.0040, 0.0090, "tip") == 0.0040, "strict_finite_min bound branch wrong")
        _req(verify.strict_finite_min(0.0040, 0.0040, "tip") == 0.0040, "strict_finite_min equal branch wrong")
        for b_args in ((0.0040, float("nan")), (float("nan"), 0.0010), (0.0040, float("inf")), (0.0040, True)):
            try:
                verify.strict_finite_min(b_args[0], b_args[1], "tip")
            except verify.CheckFailure:
                pass
            else:
                raise AssertionError(f"strict_finite_min({b_args!r}) failed to reject")

        # Boundary acceptance checks: U_duct=0.0, angle=0.0, beta=1.0, num_reeds=1
        zero_flow = verify.evaluate_venturi_collar(0.20, 1.0, 0.0, 0.0, hybrid_em_coil=False, num_reeds=1)
        _req(zero_flow["P_total_harvested_mW"] == 0.0, f"zero-flow output unexpected: {zero_flow}")

    def test_03_zoneb_certificate_bypasses_and_crashes_rejected_cleanly(self) -> None:
        orig_bytes = verify.CERT_PATH.read_bytes()
        orig_text = orig_bytes.decode("utf-8")

        byte_mutations = {
            "ZB03_5000_digit_int": orig_text.replace('"diam_mm": 200', '"diam_mm": ' + ("9" * 5000)),
            "ZB06_bool_as_int": orig_text.replace('"rejected": true', '"rejected": 1', 1),
            "ZB07_duplicate_key": orig_text.replace(
                '"certificate_version": "1.0.0",',
                '"certificate_version": "0.0.0",\n  "certificate_version": "1.0.0",',
                1,
            ),
            "ZB08_int_as_float": orig_text.replace('"reeds": 6', '"reeds": 6.0', 1),
            "ZB10_crlf": orig_text.replace("\n", "\r\n"),
            "ZB16_truncated": orig_text[:40],
            "value_tamper": orig_text.replace('"telemetry_power_margin_at_4ms_x": 11.55', '"telemetry_power_margin_at_4ms_x": 999.0', 1),
        }
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            res_dir = base / "results"
            res_dir.mkdir()
            cert_path = res_dir / "certificate.json"

            for label, bad_text in byte_mutations.items():
                cert_path.write_bytes(bad_text.encode("utf-8"))
                rc, _out, err = _run_main_inproc(cert_path, [])
                _req(rc == 1 and "mismatch" in err, f"{label}: rc={rc} err={err}")

            # ZB16 invalid UTF-8 bytes
            cert_path.write_bytes(b"\xff\xfe\x00invalid")
            rc, _out, err = _run_main_inproc(cert_path, [])
            _req(rc == 1 and "mismatch" in err, f"invalid UTF-8: rc={rc} err={err}")

            # Exact size cap boundary (MAX_CERT_BYTES accepted, MAX_CERT_BYTES + 1 rejected)
            cert_path.write_bytes(orig_bytes)
            with mock.patch.object(verify, "MAX_CERT_BYTES", len(orig_bytes)):
                verify.verify_canonical_cert_bytes(cert_path, orig_bytes)
            cert_path.write_bytes(b" " * (verify.MAX_CERT_BYTES + 1))
            rc, _out, err = _run_main_inproc(cert_path, [])
            _req(rc == 1 and "size cap" in err, f"oversized cert: rc={rc} err={err}")

            # Missing file
            cert_path.unlink()
            rc, _out, err = _run_main_inproc(cert_path, [])
            _req(rc == 1 and "mismatch" in err, f"missing cert: rc={rc} err={err}")

            # ZB15 directory at certificate path (both read & --write)
            cert_path.mkdir()
            for argv, expected_msg in (([], "not a regular file"), (["--write"], "non-regular certificate path")):
                rc, _out, err = _run_main_inproc(cert_path, argv)
                _req(rc == 1 and expected_msg in err, f"dir cert {argv}: rc={rc} err={err}")
            cert_path.rmdir()

            # ZB14 symlinked certificate file (both read & --write)
            outside = base / "outside_cert.json"
            outside.write_bytes(orig_bytes)
            cert_path.symlink_to(outside)
            for argv in ([], ["--write"]):
                rc, _out, err = _run_main_inproc(cert_path, argv)
                _req(rc == 1 and "symlink" in err, f"symlink cert {argv}: rc={rc} err={err}")
            cert_path.unlink()

            # ZB14 symlinked results/ parent directory (both read & --write)
            real_res = base / "real_results"
            real_res.mkdir()
            (real_res / "certificate.json").write_bytes(orig_bytes)
            link_res = base / "link_results"
            link_res.symlink_to(real_res, target_is_directory=True)
            for argv in ([], ["--write"]):
                rc, _out, err = _run_main_inproc(link_res / "certificate.json", argv)
                _req(rc == 1 and "symlink" in err, f"symlink dir {argv}: rc={rc} err={err}")

            # Read OSError guard
            cert_path.write_bytes(orig_bytes)
            with mock.patch.object(Path, "read_bytes", side_effect=OSError("io fail")):
                rc, _out, err = _run_main_inproc(cert_path, [])
                _req(rc == 1 and "io fail" in err, f"read_bytes OSError: rc={rc} err={err}")

    def test_04_physical_invariants_and_controls_fail_closed_under_O(self) -> None:
        # Real subprocess -O tampering of k_em (both low power and First-Law >20% violation)
        cases = [
            ("low_power", r"\bk_em\s*=\s*1\.85\b", "k_em = 0.05", "hybrid harvested power"),
            ("first_law", r"\bk_em\s*=\s*1\.85\b", "k_em = 15.0", "exceeds 20% of fluid loss"),
        ]
        for label, pat, repl, msg_sub in cases:
            with tempfile.TemporaryDirectory() as td:
                work = Path(td) / "repo"
                shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
                vpy = work / "verify.py"
                patched, count = re.subn(pat, repl, vpy.read_text(encoding="utf-8"), count=1)
                _req(count == 1, f"{label}: pattern not replaced")
                vpy.write_text(patched, encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, "-I", "-O", "-B", "verify.py", "--write"],
                    cwd=work,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                _req(proc.returncode == 1 and msg_sub in proc.stderr, f"{label}: rc={proc.returncode} stderr={proc.stderr}")

        # Exact First-Law 20% equality boundary (P_tot_mW * 1e-3 == 0.20 * P_fluid_W) must reject
        real_sf = verify.strict_finite

        def _exact_first_law_boundary(val: object, name: str, **kw: object) -> float:
            if name == "P_tot_mW":
                return 200.0
            if name == "P_fluid_W":
                return 1.0
            return real_sf(val, name, **kw)

        with mock.patch.object(verify, "strict_finite", side_effect=_exact_first_law_boundary):
            try:
                verify.evaluate_venturi_collar(0.20, 0.64, 7.0, 4.0, hybrid_em_coil=True)
            except verify.CheckFailure as exc:
                _req("exceeds 20% of fluid loss" in str(exc), f"wrong msg: {exc}")
            else:
                raise AssertionError("exact 20% First-Law boundary was not rejected")

        # In-process mocks covering every guard, boundary, & BoolOp in run_verification()
        base_eval = verify.evaluate_venturi_collar

        def _expect_run_fail(wrapper: object, label: str, expected_sub: str) -> None:
            with mock.patch.object(verify, "evaluate_venturi_collar", side_effect=wrapper):
                try:
                    verify.run_verification()
                except verify.CheckFailure as exc:
                    _req(expected_sub in str(exc), f"{label}: expected {expected_sub!r} in {str(exc)!r}")
                    return
            raise AssertionError(f"run_verification did not fail on {label}")

        def _eq_low_power(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 0.64 and a[3] == 1.8 and kw.get("hybrid_em_coil") is True:
                r = dict(r, P_total_harvested_mW=0.08)
            return r

        def _eq_piezo(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if kw.get("hybrid_em_coil") is False:
                r = dict(r, P_total_harvested_mW=0.08)
            return r

        def _eq_dp(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 0.64 and a[3] == 4.0 and kw.get("hybrid_em_coil") is True:
                r = dict(r, dP_total_Pa=6.0)
            return r

        def _straight_starts(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 1.00 and a[3] == 1.5:
                r = dict(r, P_total_harvested_mW=0.05)
            return r

        def _venturi_no_start(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 0.64 and a[3] == 1.5:
                r = dict(r, P_total_harvested_mW=0.005)
            return r

        def _low_bluff(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 0.50 and a[2] == 45.0:
                r = dict(r, dP_total_Pa=10.0)
            return r

        def _high_strain(*a: object, **kw: object) -> dict[str, float]:
            r = base_eval(*a, **kw)
            if a[1] == 0.64 and a[3] == 6.0:
                r = dict(r, peak_cfrp_strain_pct=0.30)
            return r

        _expect_run_fail(_eq_low_power, "hybrid_eq_demand", "1.8 m/s hybrid harvested power")
        _expect_run_fail(_eq_piezo, "piezo_only_eq_demand", "4.0 m/s piezo-only harvested power")
        _expect_run_fail(_eq_dp, "dp_eq_6Pa", "4.0 m/s total pressure drop")
        _expect_run_fail(_straight_starts, "straight_duct_starts_15ms", "must-fail controls")
        _expect_run_fail(_venturi_no_start, "venturi_duct_no_start_15ms", "must-fail controls")
        _expect_run_fail(_low_bluff, "bluff_low_dp", "must-fail controls")
        _expect_run_fail(_high_strain, "high_strain_6ms", "must-fail controls")


if __name__ == "__main__":
    unittest.main()
