#!/usr/bin/env python3
"""
Assertion-free R5 verification & Zone-B adversarial test suite for
`cascaded_cycle_ventilation_audit.py` (`aska-physical/venturi-collars`, Operators 2 & 3).

Runs cleanly under:
  python3 -I -B test_cascaded_cycle_ventilation_r5.py
  python3 -I -O -B test_cascaded_cycle_ventilation_r5.py
  python3 -I -B -W error test_cascaded_cycle_ventilation_r5.py
  PYTHONHASHSEED=42 python3 -I -B test_cascaded_cycle_ventilation_r5.py

Zero bare `assert` statements. Zero floats on trust paths. Zero external dependencies.
"""
from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cascaded_cycle_ventilation_audit as mod


class _LyingSequence(Sequence):
    """Adversarial Sequence whose __len__ lies relative to iteration."""

    def __getitem__(self, idx: int) -> int:
        if idx == 0:
            return 1
        raise IndexError(idx)

    def __len__(self) -> int:
        return 2


class _IntSubclass(int):
    pass


class _StrSubclass(str):
    pass


class TestPrimitivesAndJsonGuards(unittest.TestCase):
    def _assert_err(self, code: str, fn, *args, **kwargs) -> None:
        with self.assertRaises(mod.VenturiBioError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def test_exact_int_fraction_and_seq_boundaries(self) -> None:
        self.assertEqual(mod.require_exact_int(5, "x", min_val=5, max_val=5), 5)
        self._assert_err("INVALID_INT", mod.require_exact_int, True, "x")
        self._assert_err("INVALID_INT", mod.require_exact_int, _IntSubclass(3), "x")
        self._assert_err("INVALID_INT", mod.require_exact_int, 1.0, "x")
        self._assert_err("INT_TOO_SMALL", mod.require_exact_int, 4, "x", min_val=5)
        self._assert_err("INT_TOO_LARGE", mod.require_exact_int, 6, "x", max_val=5)

        self.assertEqual(mod.require_exact_fraction(0, "q", positive=False), Fraction(0, 1))
        self.assertEqual(mod.require_exact_fraction(-2, "q", positive=False), Fraction(-2, 1))
        self.assertEqual(mod.require_exact_fraction(Fraction(3, 4), "q", positive=True), Fraction(3, 4))
        self._assert_err("INVALID_FRACTION", mod.require_exact_fraction, False, "q")
        self._assert_err("INVALID_FRACTION", mod.require_exact_fraction, 0.5, "q")
        self._assert_err("INVALID_FRACTION", mod.require_exact_fraction, "1/2", "q")
        self._assert_err("NON_POSITIVE_FRACTION", mod.require_exact_fraction, 0, "q", positive=True)
        self._assert_err("NON_POSITIVE_FRACTION", mod.require_exact_fraction, Fraction(-1, 2), "q", positive=True)

        self.assertEqual(mod.require_strict_seq([1, 2], "s"), [1, 2])
        self.assertEqual(mod.require_strict_seq((3, 4), "s"), [3, 4])
        self._assert_err("INVALID_SEQ", mod.require_strict_seq, _LyingSequence(), "s")
        self._assert_err("INVALID_SEQ", mod.require_strict_seq, "abc", "s")

    def test_iterative_json_depth_digit_and_type_guards(self) -> None:
        # Exact boundary depth == 1 allowed, depth == 2 rejected when max_depth=1
        mod.validate_json_tree_iterative([1], max_depth=1)
        mod.validate_json_tree_iterative({"a": None, "b": True, "c": "ok", "d": 0}, max_depth=1)
        self._assert_err("JSON_DEPTH_EXCEEDED", mod.validate_json_tree_iterative, [[1]], max_depth=1)

        # Deep 1,500-nested Python list raises VenturiBioError (never RecursionError)
        deep: list = []
        cur = deep
        for _ in range(1500):
            nxt: list = []
            cur.append(nxt)
            cur = nxt
        self._assert_err("JSON_DEPTH_EXCEEDED", mod.validate_json_tree_iterative, deep)

        # Exact digit-count boundary: 1000 digits allowed, 1001 & huge 5000 digits rejected
        exact_1000 = int("9" * mod.MAX_INT_DIGITS)
        over_1001 = int("1" + "0" * mod.MAX_INT_DIGITS)
        huge_5000 = 10 ** 5000
        mod.validate_json_tree_iterative({"ok": exact_1000, "neg": -exact_1000})
        self._assert_err("INT_DIGITS_EXCEEDED", mod.validate_json_tree_iterative, {"bad": over_1001})
        self._assert_err("INT_DIGITS_EXCEEDED", mod.validate_json_tree_iterative, {"huge": huge_5000})

        # Non-str dict keys, floats, tuples, str subclasses
        self._assert_err("NON_STR_KEY", mod.validate_json_tree_iterative, {1: "a"})
        self._assert_err("NON_STR_KEY", mod.validate_json_tree_iterative, {_StrSubclass("a"): 1})
        self._assert_err("FORBIDDEN_JSON_TYPE", mod.validate_json_tree_iterative, {"f": 1.5})
        self._assert_err("FORBIDDEN_JSON_TYPE", mod.validate_json_tree_iterative, {"t": (1, 2)})

        # Strict JSON parser checks
        self._assert_err("INVALID_JSON_TEXT", mod.parse_strict_json, b"{}")
        self._assert_err("FLOAT_FORBIDDEN", mod.parse_strict_json, '{"x": 1.25}')
        self._assert_err("NONFINITE_CONSTANT", mod.parse_strict_json, '{"x": NaN}')
        self._assert_err("NONFINITE_CONSTANT", mod.parse_strict_json, '{"x": Infinity}')
        self._assert_err("DUPLICATE_JSON_KEY", mod.parse_strict_json, '{"a": 1, "a": 2}')
        self._assert_err("JSON_DECODE_ERROR", mod.parse_strict_json, "{bad")
        self._assert_err("JSON_DECODE_ERROR", mod.parse_strict_json, '{"huge": ' + "9" * 5000 + "}")
        self._assert_err("JSON_DEPTH_EXCEEDED", mod.parse_strict_json, "[" * 100 + "0" + "]" * 100)


class TestLinearAlgebraAndOperators(unittest.TestCase):
    def _assert_err(self, code: str, fn, *args, **kwargs) -> None:
        with self.assertRaises(mod.VenturiBioError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def test_solve_linear_exact_and_guards(self) -> None:
        # Triggers row swap (pivot != col) and exact Q solve
        sol = mod.solve_linear_exact(
            [[Fraction(0), Fraction(2)], [Fraction(3), Fraction(1)]],
            [Fraction(4), Fraction(5)],
        )
        self.assertEqual(sol, [Fraction(1), Fraction(2)])
        self._assert_err("INVALID_LINEAR_SYSTEM", mod.solve_linear_exact, [], [])
        self._assert_err("INVALID_LINEAR_SYSTEM", mod.solve_linear_exact, [[Fraction(1)]], [])
        self._assert_err("NON_SQUARE_MATRIX", mod.solve_linear_exact, [[Fraction(1), Fraction(2)]], [Fraction(1)])
        self._assert_err("SINGULAR_MATRIX", mod.solve_linear_exact, [[Fraction(1), Fraction(1)], [Fraction(2), Fraction(2)]], [Fraction(1), Fraction(2)])

    def test_pillar1_head_cascade_attenuation_and_choke(self) -> None:
        # Uniform cascades K=1,2,4,8: exact K^3 peak moment & K force reduction
        for k in (1, 2, 4, 8):
            res = mod.evaluate_head_cascade_exact(Fraction(8, 1), [Fraction(8, k)] * k)
            self.assertEqual(res["force_reduction_factor"], f"{k}/1")
            self.assertEqual(res["peak_moment_reduction_factor"], f"{k ** 3}/1")
            self.assertEqual(res["jensen_excess"], "0/1")
            self.assertTrue(res["jensen_identity_verified"])
            self.assertTrue(res["is_uniform"])

        uneq = mod.evaluate_head_cascade_exact(Fraction(8, 1), [Fraction(4, 1), Fraction(4, 3), Fraction(4, 3), Fraction(4, 3)])
        self.assertEqual(uneq["jensen_excess"], "16/3")
        self.assertEqual(uneq["peak_moment_reduction_factor"], "8/1")
        self.assertEqual(uneq["force_reduction_factor"], "3/1")
        self.assertFalse(uneq["is_uniform"])

        self._assert_err("EMPTY_STAGES", mod.evaluate_head_cascade_exact, Fraction(8, 1), [])
        self._assert_err("HEAD_CONSERVATION_MISMATCH", mod.evaluate_head_cascade_exact, Fraction(8, 1), [Fraction(3, 1), Fraction(4, 1)])

        # Cascade attenuation & alpha boundaries
        a4 = mod.evaluate_cascade_attenuation_exact(4, Fraction(1, 2), 16)
        self.assertEqual(a4["peak_outflow"], "5/32")
        self.assertEqual(a4["peak_step"], 2)
        self.assertTrue(a4["closed_form_verified"])
        self._assert_err("INVALID_ALPHA", mod.evaluate_cascade_attenuation_exact, 2, Fraction(1, 1), 8)
        self._assert_err("INVALID_ALPHA", mod.evaluate_cascade_attenuation_exact, 2, Fraction(3, 2), 8)

        # Choke contractive vs runaway
        c_ok = mod.evaluate_choke_feedback_exact(Fraction(1, 1), Fraction(1, 1), Fraction(1, 4), 5, "contractive")
        c_bad = mod.evaluate_choke_feedback_exact(Fraction(1, 1), Fraction(1, 1), Fraction(1, 4), 5, "runaway")
        self.assertEqual(c_ok["g_final"], "529177918180/1014556267661")
        self.assertTrue(c_ok["strictly_contracting"])
        self.assertTrue(c_ok["lyapunov_bound_verified"])
        self.assertFalse(c_ok["strictly_expanding"])
        self.assertTrue(c_bad["strictly_expanding"])
        self.assertFalse(c_bad["strictly_contracting"])
        self.assertFalse(c_bad["lyapunov_bound_verified"])
        self.assertGreater(Fraction(c_bad["g_final"]) / Fraction(c_ok["g_final"]), 500)

        self._assert_err("INVALID_CHOKE_MODE", mod.evaluate_choke_feedback_exact, 1, 1, Fraction(1, 4), 2, 123)
        self._assert_err("INVALID_CHOKE_MODE", mod.evaluate_choke_feedback_exact, 1, 1, Fraction(1, 4), 2, "invalid")

    def test_pillar2_kirchhoff_and_blockage_survival(self) -> None:
        # Graph validation guards
        self._assert_err("INVALID_EDGE", mod.solve_kirchhoff_circulation_exact, 3, [(0, 1, 2)], [1], [0])
        self._assert_err("SELF_LOOP_FORBIDDEN", mod.solve_kirchhoff_circulation_exact, 3, [(0, 0)], [1], [0])
        self._assert_err("DUPLICATE_EDGE", mod.solve_kirchhoff_circulation_exact, 3, [(0, 1), (1, 0)], [1, 1], [0, 0])
        self._assert_err("VECTOR_LENGTH_MISMATCH", mod.solve_kirchhoff_circulation_exact, 3, [(0, 1)], [1, 1], [0])
        self._assert_err("VECTOR_LENGTH_MISMATCH", mod.solve_kirchhoff_circulation_exact, 3, [(0, 1)], [1], [0, 0])

        # Disconnected component (including isolated node) works in Kirchhoff solver
        disc = mod.solve_kirchhoff_circulation_exact(4, [(0, 1), (1, 2), (2, 0)], [1, 1, 1], [1, 0, 0])
        self.assertEqual(disc["n_components"], 2)
        self.assertEqual(disc["beta1"], 1)
        self.assertEqual(disc["convective_power"], "1/3")
        self.assertTrue(disc["dual_solver_verified"])
        self.assertTrue(disc["kirchhoff_conservation_verified"])
        self.assertTrue(disc["cycle_basis_rank_verified"])
        self.assertTrue(disc["power_balance_verified"])

        # Blockage survival guards
        self._assert_err("TOO_FEW_EDGES", mod.evaluate_duct_blockage_survival_exact, 2, [(0, 1)])
        self._assert_err("DISCONNECTED_BASE_GRAPH", mod.evaluate_duct_blockage_survival_exact, 4, [(0, 1), (2, 3)])

        # Exact blockage check on 4-cycle: 1-edge survival 1/1, 2-edge survival 0/1
        c4 = mod.evaluate_duct_blockage_survival_exact(4, [(0, 1), (1, 2), (2, 3), (3, 0)])
        self.assertEqual(c4["cut1_survival_fraction"], "1/1")
        self.assertEqual(c4["cut2_survival_fraction"], "0/1")

    def test_pillar3_receiving_gate_and_boolop_branches(self) -> None:
        self._assert_err(
            "INVALID_LABEL",
            mod.evaluate_receiving_collar_gate,
            label=123,
            total_head=Fraction(8),
            stage_heads=[Fraction(4), Fraction(4)],
            choke_mode="contractive",
            choke_coeff=Fraction(1, 4),
            choke_steps=2,
            n_nodes=3,
            edges=[(0, 1), (1, 2), (2, 0)],
            conductances=[Fraction(1)] * 3,
            eta=[Fraction(1), Fraction(0), Fraction(0)],
        )
        self._assert_err(
            "INVALID_LABEL",
            mod.evaluate_receiving_collar_gate,
            label="   ",
            total_head=Fraction(8),
            stage_heads=[Fraction(4), Fraction(4)],
            choke_mode="contractive",
            choke_coeff=Fraction(1, 4),
            choke_steps=2,
            n_nodes=3,
            edges=[(0, 1), (1, 2), (2, 0)],
            conductances=[Fraction(1)] * 3,
            eta=[Fraction(1), Fraction(0), Fraction(0)],
        )

        # Exercise BoolOp arm: strictly_contracting=True, lyapunov_bound_verified=False -> CHOKE_NOT_CONTRACTIVE
        fake_choke = {
            "mode": "contractive",
            "strictly_contracting": True,
            "strictly_expanding": False,
            "lyapunov_bound_verified": False,
        }
        with mock.patch.object(mod, "evaluate_choke_feedback_exact", return_value=fake_choke):
            res = mod.evaluate_receiving_collar_gate(
                label="lyap_fail_arm",
                total_head=Fraction(8),
                stage_heads=[Fraction(4), Fraction(4)],
                choke_mode="contractive",
                choke_coeff=Fraction(1, 4),
                choke_steps=2,
                n_nodes=3,
                edges=[(0, 1), (1, 2), (2, 0)],
                conductances=[Fraction(1)] * 3,
                eta=[Fraction(1), Fraction(0), Fraction(0)],
            )
            self.assertFalse(res["passed"])
            self.assertEqual(res["failed_reasons"], ["CHOKE_NOT_CONTRACTIVE"])

        # Exercise BoolOp arm in build_study_payload: fixed_storage_control[1] < [0] True, [1] < [2] False
        orig_atten = mod.evaluate_cascade_attenuation_exact

        def _fake_atten(k_stages, alpha, steps):
            out = orig_atten(k_stages, alpha, steps)
            if k_stages == 8 and alpha == Fraction(8, 15):
                out["peak_outflow"] = "1/100"
            return out

        with mock.patch.object(mod, "evaluate_cascade_attenuation_exact", side_effect=_fake_atten):
            self._assert_err("STUDY_INVARIANT_FAILED", mod.build_study_payload)


class TestCertificateAndCliHardening(unittest.TestCase):
    def _assert_err(self, code: str, fn, *args, **kwargs) -> None:
        with self.assertRaises(mod.VenturiBioError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def test_verify_certificate_dict_all_rejection_paths(self) -> None:
        cert = mod.build_certificate()
        ok = mod.verify_certificate_dict(cert)
        self.assertTrue(ok["valid"])
        self.assertEqual(ok["payload_sha256"], cert["payload_sha256"])
        self.assertEqual(ok["certificate_sha256"], cert["certificate_sha256"])

        self._assert_err("CERT_NOT_DICT", mod.verify_certificate_dict, [])
        bad_keys = dict(cert)
        bad_keys["extra"] = 1
        self._assert_err("CERT_SCHEMA_KEYS", mod.verify_certificate_dict, bad_keys)

        for field, bad_val, expected_code in [
            ("schema", "wrong", "CERT_SCHEMA_MISMATCH"),
            ("study_id", "wrong", "CERT_STUDY_ID_MISMATCH"),
            ("claim_scope", "bench_measured", "CERT_CLAIM_SCOPE_MISMATCH"),
            ("payload_sha256", 123, "INVALID_DIGEST_TYPE"),
            ("payload_sha256", "abcd", "INVALID_DIGEST_LEN"),
            ("payload_sha256", "A" * 64, "INVALID_DIGEST_HEX"),
            ("payload_sha256", "0" * 64, "PAYLOAD_SHA_MISMATCH"),
            ("certificate_sha256", "0" * 64, "CERTIFICATE_SHA_MISMATCH"),
        ]:
            mut = json.loads(mod.canonical_json_bytes(cert).decode("utf-8"))
            mut[field] = bad_val
            self._assert_err(expected_code, mod.verify_certificate_dict, mut)

        # Forged self-consistent certificate with altered payload -> RECOMPUTED_PAYLOAD_DRIFT
        forged = json.loads(mod.canonical_json_bytes(cert).decode("utf-8"))
        forged["payload"]["all_passed"] = False
        forged["payload_sha256"] = hashlib.sha256(mod.canonical_json_bytes(forged["payload"])).hexdigest()
        env = {
            "schema": forged["schema"],
            "study_id": forged["study_id"],
            "claim_scope": forged["claim_scope"],
            "payload_sha256": forged["payload_sha256"],
            "payload": forged["payload"],
        }
        forged["certificate_sha256"] = hashlib.sha256(mod.canonical_json_bytes(env)).hexdigest()
        self._assert_err("RECOMPUTED_PAYLOAD_DRIFT", mod.verify_certificate_dict, forged)

    def test_file_checks_and_cli_modes(self) -> None:
        # Committed certificate must verify cleanly and match canonical bytes
        committed = mod.DEFAULT_CERT_PATH
        res = mod.check_certificate_file(committed)
        self.assertTrue(res["valid"])

        self._assert_err("INVALID_PATH_TYPE", mod.check_certificate_file, str(committed))

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            self._assert_err("CERT_FILE_NOT_FOUND", mod.check_certificate_file, td_path / "missing.json")

            # Write and verify in temp dir
            out_file = td_path / "cert.json"
            wres = mod.write_certificate_file(out_file)
            self.assertEqual(wres["certificate_sha256"], res["certificate_sha256"])
            self.assertEqual(out_file.read_bytes(), committed.read_bytes())

            # Symlink target & symlink ancestor rejected
            sym_file = td_path / "sym.json"
            sym_file.symlink_to(out_file)
            self._assert_err("SYMLINK_FORBIDDEN", mod.check_certificate_file, sym_file)

            sub_dir = td_path / "real_dir"
            sub_dir.mkdir()
            (sub_dir / "c.json").write_bytes(out_file.read_bytes())
            sym_dir = td_path / "sym_dir"
            sym_dir.symlink_to(sub_dir)
            self._assert_err("SYMLINK_ANCESTOR_FORBIDDEN", mod.check_certificate_file, sym_dir / "c.json")

            # Exact size boundary (== MAX_JSON_BYTES) allowed, (> MAX_JSON_BYTES) rejected
            with mock.patch.object(mod, "MAX_JSON_BYTES", len(out_file.read_bytes())):
                self.assertTrue(mod.check_certificate_file(out_file)["valid"])
            big = td_path / "big.json"
            big.write_bytes(b" " * (mod.MAX_JSON_BYTES + 1))
            self._assert_err("CERT_FILE_TOO_LARGE", mod.check_certificate_file, big)

            # CRLF forbidden
            crlf = td_path / "crlf.json"
            crlf.write_bytes(out_file.read_bytes().replace(b"\n", b"\r\n"))
            self._assert_err("CRLF_FORBIDDEN", mod.check_certificate_file, crlf)

            # Invalid UTF-8
            bad_utf8 = td_path / "bad_utf8.json"
            bad_utf8.write_bytes(b"\xff\xfe")
            self._assert_err("INVALID_UTF8", mod.check_certificate_file, bad_utf8)

            # Non-canonical formatting (extra spaces)
            noncanon = td_path / "noncanon.json"
            noncanon.write_text(json.dumps(json.loads(out_file.read_text(encoding="utf-8")), indent=2) + "\n", encoding="utf-8")
            self._assert_err("NON_CANONICAL_CERT_BYTES", mod.check_certificate_file, noncanon)

            # CLI in-process checks: --check, --write, --standalone, --standalone --json, error rc=2
            buf = io.StringIO()
            with mock.patch.object(sys, "stdout", buf):
                self.assertEqual(mod.main(["--check", str(out_file)]), 0)
            self.assertIn("OK VENTURI-BIO-OP23", buf.getvalue())

            buf_w = io.StringIO()
            out_cli = td_path / "cli_out.json"
            with mock.patch.object(sys, "stdout", buf_w):
                self.assertEqual(mod.main(["--write", str(out_cli)]), 0)
            self.assertIn("WROTE VENTURI-BIO-OP23", buf_w.getvalue())

            buf_s = io.StringIO()
            with mock.patch.object(sys, "stdout", buf_s):
                self.assertEqual(mod.main(["--standalone"]), 0)
            self.assertIn("all_passed=True", buf_s.getvalue())

            err_buf = io.StringIO()
            with mock.patch.object(sys, "stderr", err_buf):
                self.assertEqual(mod.main(["--check", str(noncanon)]), 2)
            self.assertIn("NON_CANONICAL_CERT_BYTES", err_buf.getvalue())

            # Subprocess --standalone --json exact byte match + 5,000-digit JSON int -> rc=2
            p_json = subprocess.run(
                [sys.executable, "-I", "-O", "-B", "-W", "error", str(HERE / "cascaded_cycle_ventilation_audit.py"), "--standalone", "--json"],
                capture_output=True,
                check=False,
            )
            self.assertEqual(p_json.returncode, 0, msg=p_json.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(p_json.stdout, committed.read_bytes())

            huge_file = td_path / "huge_int.json"
            huge_file.write_text('{"x": ' + "9" * 5000 + "}\n", encoding="utf-8")
            p_huge = subprocess.run(
                [sys.executable, "-I", "-O", "-B", "-W", "error", str(HERE / "cascaded_cycle_ventilation_audit.py"), "--check", str(huge_file)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(p_huge.returncode, 2)
            self.assertIn("REJECT", p_huge.stderr)

    def test_darwin_system_root_alias_normalization(self) -> None:
        import stat
        from types import SimpleNamespace
        from unittest import mock

        root_lnk = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)
        user_lnk = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=1000)

        def _fake_readlink(p: str) -> str:
            if p == "/var":
                return "private/var"
            if p == "/tmp":
                return "private/tmp"
            if p == "/etc":
                return "private/etc"
            raise OSError("unexpected readlink")

        with (
            mock.patch.object(mod.sys, "platform", "darwin"),
            mock.patch.object(mod.os, "lstat", return_value=root_lnk),
            mock.patch.object(mod.os, "readlink", side_effect=_fake_readlink),
        ):
            self.assertEqual(
                mod._normalize_darwin_system_prefix(Path("/var/folders/xx/cert.json")),
                Path("/private/var/folders/xx/cert.json"),
            )
            self.assertEqual(
                mod._normalize_darwin_system_prefix(Path("/tmp/cert.json")),
                Path("/private/tmp/cert.json"),
            )
            # Exact /tmp leaf or parent traversal must never normalize
            self.assertEqual(mod._normalize_darwin_system_prefix(Path("/tmp")), Path("/tmp"))
            self.assertEqual(
                mod._normalize_darwin_system_prefix(Path("/tmp/../etc/passwd")),
                Path("/tmp/../etc/passwd"),
            )
            # Guard accepts /var/... & /tmp/... when only /var or /tmp is the Darwin OS alias
            fake_symlinks = {Path("/var"), Path("/tmp"), Path("/private/var/folders/xx/evil_link")}
            with mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p in fake_symlinks):
                mod._require_no_symlink_path(Path("/var/folders/xx/cert.json"))
                mod._require_no_symlink_path(Path("/tmp/cert.json"))
                with self.assertRaises(mod.VenturiBioError) as cm_nest:
                    mod._require_no_symlink_path(Path("/var/folders/xx/evil_link/cert.json"))
                self.assertEqual(cm_nest.exception.code, "SYMLINK_ANCESTOR_FORBIDDEN")
                with self.assertRaises(mod.VenturiBioError) as cm_exact:
                    mod._require_no_symlink_path(Path("/tmp"))
                self.assertEqual(cm_exact.exception.code, "SYMLINK_FORBIDDEN")

        # Non-root owner (st_uid != 0) or unexpected target must NOT normalize and must fail closed
        with (
            mock.patch.object(mod.sys, "platform", "darwin"),
            mock.patch.object(mod.os, "lstat", return_value=user_lnk),
            mock.patch.object(mod.os, "readlink", side_effect=_fake_readlink),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(mod.VenturiBioError) as cm_uid:
                mod._require_no_symlink_path(Path("/var/folders/xx/cert.json"))
            self.assertEqual(cm_uid.exception.code, "SYMLINK_ANCESTOR_FORBIDDEN")

        with (
            mock.patch.object(mod.sys, "platform", "darwin"),
            mock.patch.object(mod.os, "lstat", return_value=root_lnk),
            mock.patch.object(mod.os, "readlink", return_value="private/evil"),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(mod.VenturiBioError) as cm_tgt:
                mod._require_no_symlink_path(Path("/var/folders/xx/cert.json"))
            self.assertEqual(cm_tgt.exception.code, "SYMLINK_ANCESTOR_FORBIDDEN")

        # Non-Darwin platform must never normalize /var or /tmp
        with (
            mock.patch.object(mod.sys, "platform", "linux"),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(mod.VenturiBioError) as cm_lin:
                mod._require_no_symlink_path(Path("/var/folders/xx/cert.json"))
            self.assertEqual(cm_lin.exception.code, "SYMLINK_ANCESTOR_FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
