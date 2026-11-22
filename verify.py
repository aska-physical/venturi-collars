#!/usr/bin/env python3
"""Deterministic Venturi fluid-loss + Pure PVDF vs. M55J/PCB-Coil Hybrid aeroelastic harvester verifier for aska-physical/venturi-collars."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CERT_PATH = ROOT / "results" / "certificate.json"


class CheckFailure(RuntimeError):
    """Raised when a physical invariant or must-fail control fails verification."""


def require(ok: bool, message: str) -> None:
    """Enforce a verification invariant regardless of Python -O optimization."""
    if not ok:
        raise CheckFailure(message)


def evaluate_venturi_collar(
    duct_diam_m: float,
    area_ratio_beta: float,
    diffuser_half_angle_deg: float,
    U_duct_m_s: float,
    hybrid_em_coil: bool = True,
    num_reeds: int = 6,
) -> dict[str, float]:
    rho_air = 1.204
    A_duct = 0.25 * math.pi * (duct_diam_m**2)
    Q_m3_s = A_duct * U_duct_m_s
    U_throat = U_duct_m_s / area_ratio_beta
    q_duct = 0.5 * rho_air * (U_duct_m_s**2)

    if diffuser_half_angle_deg <= 8.0:
        K_venturi = 0.04 * (1.0 / area_ratio_beta**2 - 1.0) + 0.13 * ((1.0 / area_ratio_beta - 1.0) ** 2)
    else:
        K_venturi = ((1.0 / (0.61 * area_ratio_beta) - 1.0) ** 2)

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
            "f_flutter_Hz": round(f_flutter_Hz, 2),
            "dP_total_Pa": round(dP_total_Pa, 3),
            "P_fluid_loss_mW": round(P_fluid_W * 1e3, 2),
            "P_piezo_only_mW": 0.0,
            "P_total_harvested_mW": 0.0,
            "peak_cfrp_strain_pct": 0.0,
        }

    vel_factor = math.sqrt((U_throat**2 - U_crit_throat**2) / (U_crit_throat**2 + 6.0))
    tip_amp_m = min(0.0040, 0.0026 * vel_factor)
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

    P_tot_mW = P_piezo_mW + P_em_mW
    require(
        P_tot_mW * 1e-3 < 0.20 * P_fluid_W,
        f"harvested power {P_tot_mW:.4f} mW exceeds 20% of fluid loss {P_fluid_W * 1e3:.2f} mW",
    )

    return {
        "U_duct_m_s": U_duct_m_s,
        "U_throat_m_s": round(U_throat, 3),
        "U_crit_throat_m_s": round(U_crit_throat, 3),
        "f_flutter_Hz": round(f_flutter_Hz, 2),
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
    ]
    failed_controls = [c["control"] for c in controls if not c["rejected"]]
    require(not failed_controls, f"must-fail controls did not reject: {failed_controls}")

    return {
        "repository": "aska-physical/venturi-collars",
        "certificate_version": "1.0.0",
        "duct_geometry": {"diam_mm": 200, "throat_area_ratio_beta": 0.64, "diffuser_half_angle_deg": 7.0, "reeds": 6},
        "pure_pvdf_4ms_negative_finding_mW": piezo_only_4ms["P_total_harvested_mW"],
        "hybrid_cfrp_pcb_coil_sweep": sweep_hybrid,
        "telemetry_power_margin_at_4ms_x": round(sweep_hybrid[2]["P_total_harvested_mW"] / sensor_demand_mW, 2),
        "must_fail_controls": controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    cert = run_verification()
    if args.write:
        CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CERT_PATH.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not CERT_PATH.exists() or json.loads(CERT_PATH.read_text(encoding="utf-8")) != cert:
        print("[FAIL] results/certificate.json mismatch or missing", file=sys.stderr)
        return 1
    passed_controls = sum(1 for c in cert["must_fail_controls"] if c["rejected"])
    total_controls = len(cert["must_fail_controls"])
    print(f"[PASS] venturi-collars Venturi dP + PVDF negative finding + Hybrid CFRP-Coil checks ({passed_controls}/{total_controls} controls): OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
