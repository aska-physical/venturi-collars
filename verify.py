#!/usr/bin/env python3
"""Deterministic Venturi fluid-loss + Pure PVDF vs. M55J/PCB-Coil Hybrid aeroelastic harvester verifier for aska-physical/venturi-collars (v1.1.0)."""

from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CERT_PATH = ROOT / "results" / "certificate.json"
MAX_CERT_BYTES = 1_048_576

# Standard dry air at 20 C (rho = 1.204 kg/m^3, gamma = 1.4, R = 287.05 J/(kg*K))
RHO_AIR_KG_M3 = 1.204
GAMMA_AIR = 1.4
R_AIR_J_KG_K = 287.05
T_AIR_K = 293.15
A_SOUND_M_S = math.sqrt(GAMMA_AIR * R_AIR_J_KG_K * T_AIR_K)
MAX_INCOMPRESSIBLE_MACH = 0.30


class CheckFailure(RuntimeError):
    """Raised when a physical invariant, finite-value guard, or canonical certificate check fails."""


def require(ok: bool, message: str) -> None:
    """Enforce a verification invariant regardless of Python -O optimization."""
    if not ok:
        raise CheckFailure(message)


def strict_finite(
    value: Any,
    name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    """Validate that a numeric input/output is an exact int/float (not bool) and finite."""
    require(type(value) in (int, float), f"{name} must be finite number, got {type(value).__name__}")
    val = float(value)
    require(math.isfinite(val), f"{name} must be finite, got {value!r}")
    if positive:
        require(val > 0.0, f"{name} must be positive, got {val!r}")
    if non_negative:
        require(val >= 0.0, f"{name} must be non-negative, got {val!r}")
    return val


def strict_finite_min(bound: Any, value: Any, name: str) -> float:
    """NaN-safe upper clamp: rejects non-finite arguments instead of silently swallowing NaN."""
    fb = strict_finite(bound, f"{name}.bound")
    fv = strict_finite(value, f"{name}.value")
    return fb if fb <= fv else fv


def strict_finite_max(bound: Any, value: Any, name: str) -> float:
    """NaN-safe lower clamp: rejects non-finite arguments instead of silently swallowing NaN."""
    fb = strict_finite(bound, f"{name}.bound")
    fv = strict_finite(value, f"{name}.value")
    return fb if fb >= fv else fv


def render_canonical_cert_bytes(cert: dict[str, Any]) -> bytes:
    """Render deterministic LF-terminated canonical JSON bytes, forbidding NaN/Infinity."""
    return (json.dumps(cert, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _require_no_symlink_cert_path(cert_path: Path) -> None:
    require(not os.path.islink(cert_path.parent), "results/certificate.json mismatch or missing: symlink parent directory forbidden")
    require(not os.path.islink(cert_path), "results/certificate.json mismatch or missing: symlink certificate path forbidden")


def verify_canonical_cert_bytes(cert_path: Path, expected_bytes: bytes) -> None:
    """Fail-closed canonical-byte certificate verifier closing Zone-B dict/JSON/symlink bypasses."""
    _require_no_symlink_cert_path(cert_path)
    try:
        st = os.lstat(cert_path)
    except OSError as exc:
        raise CheckFailure(f"results/certificate.json mismatch or missing: {exc}") from exc
    require(stat.S_ISREG(st.st_mode), "results/certificate.json mismatch or missing: not a regular file")
    require(st.st_size <= MAX_CERT_BYTES, "results/certificate.json mismatch or missing: exceeds size cap")
    try:
        raw = cert_path.read_bytes()
    except OSError as exc:
        raise CheckFailure(f"results/certificate.json mismatch or missing: {exc}") from exc
    require(
        hmac.compare_digest(raw, expected_bytes),
        "results/certificate.json mismatch or missing: canonical byte mismatch",
    )


def write_canonical_cert_bytes(cert_path: Path, payload: bytes) -> None:
    """Write canonical certificate bytes without following symlinks or overwriting non-regular files."""
    _require_no_symlink_cert_path(cert_path)
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(cert_path):
        st = os.lstat(cert_path)
        require(stat.S_ISREG(st.st_mode), "refusing to overwrite non-regular certificate path")
    cert_path.write_bytes(payload)


def compute_venturi_loss_coeff(
    area_ratio_beta: float,
    diffuser_half_angle_deg: float,
    f_darcy: float = 0.020,
) -> tuple[float, float]:
    """Continuous conical Venturi minor-loss coefficient K_venturi(beta, 2*theta) referenced to duct dynamic head.

    Combines smooth contraction loss, conical wall Darcy friction integrated along slant length,
    Gibson/Idelchik conical expansion-stall factor with Kline-Reneau (2*theta, AR=1/beta) stall
    intensification, and smooth sharp-baffle vena-contracta onset (C_c: 1.0 -> 0.61 over 15..45 deg).
    Replaces v1.0.0's flat <=8 deg constant and discontinuous Borda-Carnot cliff.
    """
    area_ratio_beta = strict_finite(area_ratio_beta, "area_ratio_beta", positive=True)
    require(area_ratio_beta <= 1.0, f"area_ratio_beta must be <= 1.0, got {area_ratio_beta!r}")
    diffuser_half_angle_deg = strict_finite(diffuser_half_angle_deg, "diffuser_half_angle_deg", non_negative=True)
    require(diffuser_half_angle_deg <= 90.0, f"diffuser_half_angle_deg must be <= 90.0, got {diffuser_half_angle_deg!r}")
    f_darcy = strict_finite(f_darcy, "f_darcy", non_negative=True)

    if area_ratio_beta == 1.0:
        return 0.0, 0.0

    require(
        diffuser_half_angle_deg > 0.0,
        f"diffuser_half_angle_deg must be > 0 when area_ratio_beta < 1.0, got {diffuser_half_angle_deg!r}",
    )
    th_rad = math.radians(diffuser_half_angle_deg)
    ar = 1.0 / area_ratio_beta
    k_contr = 0.04 * (ar**2 - 1.0)
    k_fric = (f_darcy / (8.0 * math.sin(th_rad))) * (ar**2 - 1.0)

    if diffuser_half_angle_deg >= 45.0:
        k_exp_base = 1.0
    else:
        k_exp_base = strict_finite_min(1.0, 3.2 * (math.tan(th_rad) ** 1.25), "k_exp_base")

    # Kline-Reneau area-ratio stall intensification: larger AR=1/beta separates at smaller full angle 2*theta
    two_theta_deg = 2.0 * diffuser_half_angle_deg
    two_theta_stall_deg = 16.0 / ((ar - 1.0) ** 0.35)
    stall_excess = strict_finite_max(0.0, (two_theta_deg - two_theta_stall_deg) / two_theta_stall_deg, "stall_excess")
    k_exp = strict_finite_min(1.0, k_exp_base * (1.0 + 0.5 * stall_excess), "k_exp")

    # Smooth vena-contracta ramp for sharply separated diffusers/baffles (15 deg -> 45 deg: C_c = 1.0 -> 0.61)
    if diffuser_half_angle_deg <= 15.0:
        c_c = 1.0
    else:
        s_vc = strict_finite_min(1.0, (diffuser_half_angle_deg - 15.0) / 30.0, "s_vc")
        c_c = 1.0 - s_vc * (1.0 - 0.61)

    k_diff = k_fric + k_exp * ((ar / c_c - 1.0) ** 2)
    return strict_finite(k_contr + k_diff, "K_venturi", non_negative=True), k_exp


def supercritical_vel_factor(
    U_throat_m_s: float,
    U_crit_throat_m_s: float,
    U_sat_m_s: float = 0.0,
) -> float:
    """Dimensionless supercritical Hopf flutter amplitude factor sqrt((U_t^2 - U_c^2) / (U_c^2 + U_sat^2)).

    Defaults to U_sat_m_s = 0.0 (pure dimensionless sqrt((U_t/U_c)^2 - 1)), removing v1.0.0's
    unexplained dimensional '+ 6.0' (m^2/s^2) denominator constant.
    """
    u_t = strict_finite(U_throat_m_s, "U_throat_m_s", non_negative=True)
    u_c = strict_finite(U_crit_throat_m_s, "U_crit_throat_m_s", positive=True)
    u_s = strict_finite(U_sat_m_s, "U_sat_m_s", non_negative=True)
    if u_t <= u_c:
        return 0.0
    return strict_finite(math.sqrt((u_t**2 - u_c**2) / (u_c**2 + u_s**2)), "vel_factor", non_negative=True)


def evaluate_venturi_collar(
    duct_diam_m: float,
    area_ratio_beta: float,
    diffuser_half_angle_deg: float,
    U_duct_m_s: float,
    hybrid_em_coil: bool = True,
    num_reeds: int = 6,
    U_sat_m_s: float = 0.0,
) -> dict[str, float]:
    duct_diam_m = strict_finite(duct_diam_m, "duct_diam_m", positive=True)
    area_ratio_beta = strict_finite(area_ratio_beta, "area_ratio_beta", positive=True)
    require(area_ratio_beta <= 1.0, f"area_ratio_beta must be <= 1.0, got {area_ratio_beta!r}")
    diffuser_half_angle_deg = strict_finite(diffuser_half_angle_deg, "diffuser_half_angle_deg", non_negative=True)
    require(diffuser_half_angle_deg <= 90.0, f"diffuser_half_angle_deg must be <= 90.0, got {diffuser_half_angle_deg!r}")
    U_duct_m_s = strict_finite(U_duct_m_s, "U_duct_m_s", non_negative=True)
    require(type(hybrid_em_coil) is bool, "hybrid_em_coil must be bool")
    require(type(num_reeds) is int and num_reeds >= 1, "num_reeds must be positive int")
    U_sat_m_s = strict_finite(U_sat_m_s, "U_sat_m_s", non_negative=True)

    rho_air = RHO_AIR_KG_M3
    A_duct = 0.25 * math.pi * (duct_diam_m**2)
    Q_m3_s = A_duct * U_duct_m_s
    U_throat = U_duct_m_s / area_ratio_beta
    Ma_throat = strict_finite(U_throat / A_SOUND_M_S, "Ma_throat", non_negative=True)
    require(
        Ma_throat <= MAX_INCOMPRESSIBLE_MACH,
        f"throat Mach number {Ma_throat:.4f} exceeds incompressible validity limit {MAX_INCOMPRESSIBLE_MACH:.2f}",
    )
    q_duct = 0.5 * rho_air * (U_duct_m_s**2)

    K_venturi, diffuser_stall_factor = compute_venturi_loss_coeff(area_ratio_beta, diffuser_half_angle_deg)

    reed_L_m, reed_W_m = 0.070, 0.030
    t_cfrp_m, t_pvdf_tot = 35e-6, 84e-6
    A_reeds_proj = num_reeds * reed_W_m * 0.0035
    dP_reed_Pa = 0.5 * rho_air * (U_throat**2) * 0.90 * (A_reeds_proj / (area_ratio_beta * A_duct))
    dP_total_Pa = K_venturi * q_duct + dP_reed_Pa
    P_fluid_W = Q_m3_s * dP_total_Pa

    E_c, E_p = 95.0e9, 2.8e9
    rho_c, rho_p = 1626.0, 1780.0
    I_core = reed_W_m * (t_cfrp_m**3) / 12.0
    I_pvdf = 2.0 * reed_W_m * ((t_pvdf_tot**3) / 12.0 + t_pvdf_tot * ((0.5 * t_cfrp_m + 0.5 * t_pvdf_tot) ** 2))
    D_bend = E_c * I_core + E_p * I_pvdf
    m_tip = 0.00035 if hybrid_em_amp_enabled(hybrid_em_coil) else 0.0
    m_eff_L = reed_W_m * (rho_c * t_cfrp_m + 2.0 * rho_p * t_pvdf_tot) + (m_tip / (0.24 * reed_L_m))

    omega_1 = (1.875104**2 / (reed_L_m**2)) * math.sqrt(D_bend / m_eff_L)
    f_flutter_Hz = omega_1 / (2.0 * math.pi)
    U_crit_throat = 0.95 * math.sqrt(D_bend / (rho_air * reed_W_m * (reed_L_m**3)))

    if U_throat <= U_crit_throat:
        return {
            "U_duct_m_s": U_duct_m_s,
            "U_throat_m_s": round(U_throat, 3),
            "U_crit_throat_m_s": round(U_crit_throat, 3),
            "Ma_throat": round(Ma_throat, 5),
            "K_venturi": round(K_venturi, 4),
            "diffuser_stall_factor": round(diffuser_stall_factor, 4),
            "f_flutter_Hz": round(f_flutter_Hz, 2),
            "tip_amp_mm": 0.0,
            "dP_total_Pa": round(dP_total_Pa, 3),
            "P_fluid_loss_mW": round(P_fluid_W * 1e3, 2),
            "P_piezo_only_mW": 0.0,
            "P_total_harvested_mW": 0.0,
            "peak_cfrp_strain_pct": 0.0,
        }

    vel_factor = supercritical_vel_factor(U_throat, U_crit_throat, U_sat_m_s=U_sat_m_s)
    tip_amp_m = strict_finite_min(0.0040, 0.0026 * vel_factor, "tip_amp_m")
    y_max = 0.5 * t_cfrp_m + t_pvdf_tot
    peak_strain = 3.52 * tip_amp_m * y_max / (reed_L_m**2)
    eps_rms = 0.55 * peak_strain

    d31, eps_0, eps_r = 23.0e-12, 8.854187817e-12, 12.0
    C_p = 6.0 * eps_r * eps_0 * (reed_L_m * reed_W_m) / 28e-6
    R_opt = 1.0 / (omega_1 * C_p)
    I_rms = omega_1 * d31 * E_p * eps_rms * (6.0 * reed_L_m * reed_W_m)
    P_piezo_mW = num_reeds * (0.78 * 0.5 * (I_rms**2) * R_opt) * 1e3

    P_em_mW = 0.0
    if hybrid_em_coil:
        v_tip_rms = (omega_1 * tip_amp_m) / math.sqrt(2.0)
        k_em = 1.85
        R_coil = 42.0
        P_em_per_reed_W = 0.82 * ((k_em * v_tip_rms) ** 2) / (4.0 * R_coil)
        P_em_mW = num_reeds * P_em_per_reed_W * 1e3

    P_tot_mW = strict_finite(P_piezo_mW + P_em_mW, "P_tot_mW", non_negative=True)
    P_fluid_W = strict_finite(P_fluid_W, "P_fluid_W", positive=True)
    require(
        P_tot_mW * 1e-3 < 0.20 * P_fluid_W,
        f"harvested power {P_tot_mW:.4f} mW exceeds 20% of fluid loss {P_fluid_W * 1e3:.2f} mW",
    )

    return {
        "U_duct_m_s": U_duct_m_s,
        "U_throat_m_s": round(U_throat, 3),
        "U_crit_throat_m_s": round(U_crit_throat, 3),
        "Ma_throat": round(Ma_throat, 5),
        "K_venturi": round(K_venturi, 4),
        "diffuser_stall_factor": round(diffuser_stall_factor, 4),
        "f_flutter_Hz": round(f_flutter_Hz, 2),
        "tip_amp_mm": round(tip_amp_m * 1e3, 3),
        "dP_total_Pa": round(dP_total_Pa, 3),
        "P_fluid_loss_mW": round(P_fluid_W * 1e3, 2),
        "P_piezo_only_mW": round(P_piezo_mW, 4),
        "P_total_harvested_mW": round(P_tot_mW, 4),
        "peak_cfrp_strain_pct": round(peak_strain * 100.0, 4),
    }


def hybrid_em_amp_enabled(flag: bool) -> bool:
    return flag


def run_verification() -> dict[str, Any]:
    sweep_hybrid = [evaluate_venturi_collar(0.20, 0.64, 7.0, u, hybrid_em_coil=True) for u in (1.8, 2.5, 4.0, 6.0)]
    piezo_only_4ms = evaluate_venturi_collar(0.20, 0.64, 7.0, 4.0, hybrid_em_coil=False)
    straight_duct_15ms = evaluate_venturi_collar(0.20, 1.00, 7.0, 1.5, hybrid_em_coil=True)
    venturi_duct_15ms = evaluate_venturi_collar(0.20, 0.64, 7.0, 1.5, hybrid_em_coil=True)
    bluff_orifice_4ms = evaluate_venturi_collar(0.20, 0.50, 45.0, 4.0, hybrid_em_coil=True)
    stalled_15deg_4ms = evaluate_venturi_collar(0.20, 0.64, 15.0, 4.0, hybrid_em_coil=True)
    stalled_25deg_4ms = evaluate_venturi_collar(0.20, 0.64, 25.0, 4.0, hybrid_em_coil=True)
    opt_4deg_4ms = evaluate_venturi_collar(0.20, 0.64, 4.0, 4.0, hybrid_em_coil=True)

    # Quantify the v1.0.0 unexplained +6.0 m^2/s^2 denominator distortion at 1.8 m/s turndown
    u_t_18 = sweep_hybrid[0]["U_throat_m_s"]
    u_c_18 = sweep_hybrid[0]["U_crit_throat_m_s"]
    vf_clean_18 = supercritical_vel_factor(u_t_18, u_c_18, U_sat_m_s=0.0)
    vf_legacy_plus6_18 = supercritical_vel_factor(u_t_18, u_c_18, U_sat_m_s=math.sqrt(6.0))
    legacy_plus6_power_ratio = (vf_legacy_plus6_18 / vf_clean_18) ** 2

    # Confirm high-Mach choked/compressible throat (beta=0.05 at 6 m/s -> U_t=120 m/s, Ma=0.35 > 0.30) is rejected
    high_mach_rejected = False
    try:
        evaluate_venturi_collar(0.20, 0.05, 7.0, 6.0, hybrid_em_coil=True)
    except CheckFailure as exc:
        high_mach_rejected = "Mach" in str(exc)

    sensor_demand_mW = 0.08
    require(
        sweep_hybrid[0]["P_total_harvested_mW"] > sensor_demand_mW,
        f"1.8 m/s hybrid harvested power {sweep_hybrid[0]['P_total_harvested_mW']} mW <= {sensor_demand_mW} mW demand",
    )
    require(
        piezo_only_4ms["P_total_harvested_mW"] < sensor_demand_mW,
        f"4.0 m/s piezo-only harvested power {piezo_only_4ms['P_total_harvested_mW']} mW >= {sensor_demand_mW} mW demand",
    )
    require(
        sweep_hybrid[2]["dP_total_Pa"] < 6.0,
        f"4.0 m/s total pressure drop {sweep_hybrid[2]['dP_total_Pa']} Pa >= 6.0 Pa limit",
    )

    controls = [
        {"control": "harvested_power_violates_first_law_fluid_work", "rejected": all(r["P_total_harvested_mW"] < 0.15 * r["P_fluid_loss_mW"] for r in sweep_hybrid)},
        {"control": "pure_pvdf_film_alone_meets_150uW_continuous_co2_node_at_4ms", "rejected": piezo_only_4ms["P_total_harvested_mW"] < sensor_demand_mW},
        {"control": "unaccelerated_straight_duct_starts_at_1.5ms_turndown", "rejected": straight_duct_15ms["P_total_harvested_mW"] == 0.0 and venturi_duct_15ms["P_total_harvested_mW"] > 0.01},
        {"control": "abrupt_45deg_baffle_meets_15Pa_hvac_static_pressure_limit", "rejected": bluff_orifice_4ms["dP_total_Pa"] > 15.0 and sweep_hybrid[2]["dP_total_Pa"] < 6.0},
        {"control": "reed_exceeds_m55j_0.8pct_ultimate_strain_at_6ms", "rejected": sweep_hybrid[3]["peak_cfrp_strain_pct"] < 0.25},
        {"control": "unexplained_plus6_denominator_preserves_turndown_harvest_within_50pct", "rejected": legacy_plus6_power_ratio < 0.50},
        {"control": "stalled_15deg_diffuser_matches_7deg_minor_loss", "rejected": opt_4deg_4ms["K_venturi"] < sweep_hybrid[2]["K_venturi"] < stalled_15deg_4ms["K_venturi"] < stalled_25deg_4ms["K_venturi"] and stalled_15deg_4ms["dP_total_Pa"] > 1.5 * sweep_hybrid[2]["dP_total_Pa"]},
        {"control": "incompressible_model_accepts_high_mach_choked_throat", "rejected": high_mach_rejected and sweep_hybrid[3]["Ma_throat"] < 0.05},
    ]
    failed_controls = [c["control"] for c in controls if not c["rejected"]]
    require(not failed_controls, f"must-fail controls did not reject: {failed_controls}")

    return {
        "repository": "aska-physical/venturi-collars",
        "certificate_version": "1.1.0",
        "duct_geometry": {"diam_mm": 200, "throat_area_ratio_beta": 0.64, "diffuser_half_angle_deg": 7.0, "reeds": 6},
        "pure_pvdf_4ms_negative_finding_mW": piezo_only_4ms["P_total_harvested_mW"],
        "hybrid_cfrp_pcb_coil_sweep": sweep_hybrid,
        "physical_hardening_diagnostics": {
            "a_sound_20C_m_s": round(A_SOUND_M_S, 3),
            "incompressible_mach_limit": MAX_INCOMPRESSIBLE_MACH,
            "turndown_1p8ms_legacy_plus6_power_ratio": round(legacy_plus6_power_ratio, 4),
            "diffuser_loss_4deg_opt_K": opt_4deg_4ms["K_venturi"],
            "diffuser_loss_7deg_design_K": sweep_hybrid[2]["K_venturi"],
            "diffuser_loss_15deg_stall_K": stalled_15deg_4ms["K_venturi"],
            "diffuser_loss_25deg_stall_K": stalled_25deg_4ms["K_venturi"],
            "dP_15deg_stall_at_4ms_Pa": stalled_15deg_4ms["dP_total_Pa"],
        },
        "telemetry_power_margin_at_4ms_x": round(sweep_hybrid[2]["P_total_harvested_mW"] / sensor_demand_mW, 2),
        "must_fail_controls": controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        cert = run_verification()
        expected_bytes = render_canonical_cert_bytes(cert)
        if args.write:
            write_canonical_cert_bytes(CERT_PATH, expected_bytes)
        verify_canonical_cert_bytes(CERT_PATH, expected_bytes)
    except CheckFailure as exc:
        print(f"[FAIL] CheckFailure: {exc}", file=sys.stderr)
        return 1
    passed_controls = sum(1 for c in cert["must_fail_controls"] if c["rejected"])
    total_controls = len(cert["must_fail_controls"])
    print(f"[PASS] venturi-collars v1.1.0 Venturi dP + Stall + Mach + PVDF negative finding + Hybrid CFRP-Coil checks ({passed_controls}/{total_controls} controls): OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
