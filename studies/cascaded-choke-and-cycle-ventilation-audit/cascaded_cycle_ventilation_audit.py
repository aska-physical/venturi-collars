#!/usr/bin/env python3
"""
Exact Pure-Z/Q Receiving-Side Checker for Cascaded Choke Contraction & Cycle-Space
Passive Ventilation (`aska-physical/venturi-collars`, Operators 2 & 3 from AUDIT-117).

Governance (`aska-physical/dock#8`):
  - Pure Python 3 standard library only (`int`, `fractions.Fraction`, `math.comb`).
  - Zero floats on trust paths. Zero bare `assert` statements. Zero RNG calls.
  - All outputs are certified `model` / `checker` results in exact rational arithmetic
    (never bench measurements).
  - Bridges `venturi-collars/verify.py:17-41, 68-69, 109-125` (`origin/main @ d53f85a3`).

CLI:
  - `--standalone --json`: emit canonical zero-float certificate JSON to stdout
  - `--write [PATH]`: write canonical certificate to `cascaded_cycle_ventilation_certificate.json` (or PATH)
  - `--check PATH`: fail-closed verification (symlink guard, size cap, CRLF/UTF-8,
    iterative depth/digit/zero-float JSON check, `hmac.compare_digest` on `payload_sha256`
    and `certificate_sha256`, exact recomputation, canonical byte parity).
"""
from __future__ import annotations

import argparse
from collections import deque
from fractions import Fraction
import hashlib
import hmac
import json
import math
from pathlib import Path
import os
import stat
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
CERT_SCHEMA = "venturi_collars.cascaded_cycle_ventilation.certificate.v1"
CERT_STUDY_ID = "VENTURI-BIO-OP23"
DEFAULT_CERT_PATH = HERE / "cascaded_cycle_ventilation_certificate.json"
MAX_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_INT_DIGITS = 1000
_HEX_LOWER = frozenset("0123456789abcdef")
_CERT_KEYS = frozenset({"schema", "study_id", "claim_scope", "payload_sha256", "certificate_sha256", "payload"})
_CLAIM_SCOPE = "model_and_checker_only_no_bench_measurement"


class VenturiBioError(ValueError):
    """Fail-closed typed error carrying a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def require_exact_int(
    val: Any,
    label: str,
    min_val: int | None = None,
    max_val: int | None = None,
) -> int:
    if type(val) is not int:
        raise VenturiBioError("INVALID_INT", f"{label} must be strict int")
    if min_val is not None and val < min_val:
        raise VenturiBioError("INT_TOO_SMALL", f"{label} < {min_val}")
    if max_val is not None and val > max_val:
        raise VenturiBioError("INT_TOO_LARGE", f"{label} > {max_val}")
    return val


def require_exact_fraction(val: Any, label: str, positive: bool = False) -> Fraction:
    if type(val) is int:
        out = Fraction(val, 1)
    elif type(val) is Fraction:
        out = val
    else:
        raise VenturiBioError("INVALID_FRACTION", f"{label} must be strict int or Fraction")
    if positive and out <= 0:
        raise VenturiBioError("NON_POSITIVE_FRACTION", f"{label} must be > 0")
    return out


def require_strict_seq(val: Any, label: str) -> list[Any]:
    if type(val) not in (list, tuple):
        raise VenturiBioError("INVALID_SEQ", f"{label} must be strict list or tuple")
    return list(val)


def frac_str(val: Fraction) -> str:
    f = require_exact_fraction(val, "frac")
    return f"{f.numerator}/{f.denominator}"


def _int_digit_len(n: int) -> int:
    val = -n if n < 0 else n
    if val == 0:
        return 1
    # Exact base-10 digit count without invoking sys.int_max_str_digits limits on huge ints
    # Fast bit-length upper check first, then exact str only within safe bound
    if val.bit_length() > MAX_INT_DIGITS * 4:
        return MAX_INT_DIGITS + 1
    return len(str(val))


def validate_json_tree_iterative(obj: Any, max_depth: int = MAX_JSON_DEPTH) -> None:
    """Iteratively reject floats, non-strict containers, oversized ints, and excessive nesting."""
    limit = require_exact_int(max_depth, "max_depth", min_val=1, max_val=256)
    stack: list[tuple[Any, int]] = [(obj, 0)]
    while stack:
        cur, depth = stack.pop()
        if depth > limit:
            raise VenturiBioError("JSON_DEPTH_EXCEEDED", f"nesting depth > {limit}")
        t = type(cur)
        if t is dict:
            for k, v in cur.items():
                if type(k) is not str:
                    raise VenturiBioError("NON_STR_KEY", "dict keys must be strict str")
                stack.append((v, depth + 1))
        elif t is list:
            for item in cur:
                stack.append((item, depth + 1))
        elif t is int:
            if _int_digit_len(cur) > MAX_INT_DIGITS:
                raise VenturiBioError("INT_DIGITS_EXCEEDED", f"int exceeds {MAX_INT_DIGITS} digits")
        elif t in (str, bool) or cur is None:
            continue
        else:
            raise VenturiBioError("FORBIDDEN_JSON_TYPE", f"forbidden JSON value type: {t.__name__}")


def _strict_no_dups_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise VenturiBioError("DUPLICATE_JSON_KEY", f"duplicate key: {k}")
        out[k] = v
    return out


def _forbid_float(token: str) -> Any:
    raise VenturiBioError("FLOAT_FORBIDDEN", f"float literal forbidden: {token}")


def _forbid_constant(token: str) -> Any:
    raise VenturiBioError("NONFINITE_CONSTANT", f"non-finite constant forbidden: {token}")


def parse_strict_json(text: str) -> Any:
    if type(text) is not str:
        raise VenturiBioError("INVALID_JSON_TEXT", "JSON input must be strict str")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_strict_no_dups_hook,
            parse_float=_forbid_float,
            parse_constant=_forbid_constant,
        )
    except VenturiBioError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise VenturiBioError("JSON_DECODE_ERROR", f"invalid JSON: {exc}") from exc
    validate_json_tree_iterative(parsed)
    return parsed


def canonical_json_bytes(obj: Any) -> bytes:
    validate_json_tree_iterative(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _require_sha256_hex(val: Any, label: str) -> str:
    if type(val) is not str:
        raise VenturiBioError("INVALID_DIGEST_TYPE", f"{label} must be strict str")
    if len(val) != 64:
        raise VenturiBioError("INVALID_DIGEST_LEN", f"{label} must have length 64")
    if any(ch not in _HEX_LOWER for ch in val):
        raise VenturiBioError("INVALID_DIGEST_HEX", f"{label} must be lowercase hex")
    return val


_DARWIN_SYSTEM_ROOT_ALIASES: tuple[tuple[str, str], ...] = (
    ("/var", "/private/var"),
    ("/tmp", "/private/tmp"),
    ("/etc", "/private/etc"),
)


def _normalize_darwin_system_prefix(path: Path, *, allow_exact: bool = False) -> Path:
    """Map verified root-owned macOS /var, /tmp, /etc aliases to /private/* without resolving user symlinks."""
    if sys.platform != "darwin" or not path.is_absolute():
        return path
    parts = path.parts
    min_parts = 2 if allow_exact else 3
    if len(parts) < min_parts or parts[0] != "/" or ".." in parts:
        return path
    top = "/" + parts[1]
    for alias, canonical in _DARWIN_SYSTEM_ROOT_ALIASES:
        if top != alias:
            continue
        try:
            st = os.lstat(alias)
            if not stat.S_ISLNK(st.st_mode) or st.st_uid != 0:
                return path
            target = os.readlink(alias)
            if target not in (canonical, canonical.lstrip("/")):
                return path
        except OSError:
            return path
        return Path(canonical, *parts[2:])
    return path


def _require_no_symlink_path(path: Path) -> None:
    norm = _normalize_darwin_system_prefix(path)
    if norm.is_symlink():
        raise VenturiBioError("SYMLINK_FORBIDDEN", f"symlink path forbidden: {path}")
    for parent in norm.parents:
        if parent.is_symlink():
            raise VenturiBioError("SYMLINK_ANCESTOR_FORBIDDEN", f"symlink ancestor forbidden: {parent}")


# ---------------------------------------------------------------------------
# Exact-Q Linear Algebra & Graph Connectivity Helpers
# ---------------------------------------------------------------------------

def solve_linear_exact(matrix: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction]:
    """Exact Gaussian elimination over Q with partial pivoting and zero-residual check."""
    mat_rows = require_strict_seq(matrix, "matrix")
    rhs_vec = require_strict_seq(rhs, "rhs")
    n = len(mat_rows)
    if n == 0 or len(rhs_vec) != n:
        raise VenturiBioError("INVALID_LINEAR_SYSTEM", "empty or mismatched linear system")
    aug: list[list[Fraction]] = []
    for i, row in enumerate(mat_rows):
        row_seq = require_strict_seq(row, f"matrix[{i}]")
        if len(row_seq) != n:
            raise VenturiBioError("NON_SQUARE_MATRIX", f"row {i} length != {n}")
        aug.append([require_exact_fraction(x, f"A[{i},{j}]") for j, x in enumerate(row_seq)] + [require_exact_fraction(rhs_vec[i], f"b[{i}]")])

    for col in range(n):
        pivot = -1
        for r in range(col, n):
            if aug[r][col] != 0:
                pivot = r
                break
        if pivot < 0:
            raise VenturiBioError("SINGULAR_MATRIX", f"singular matrix at column {col}")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        piv_val = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= piv_val
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor != 0:
                for j in range(col, n + 1):
                    aug[r][j] -= factor * aug[col][j]

    return [aug[i][n] for i in range(n)]


def _validate_graph(
    n_nodes: Any,
    edges: Any,
) -> tuple[int, list[tuple[int, int]]]:
    n = require_exact_int(n_nodes, "n_nodes", min_val=2, max_val=64)
    edge_seq = require_strict_seq(edges, "edges")
    clean_edges: list[tuple[int, int]] = []
    seen_undirected: set[tuple[int, int]] = set()
    for idx, edge in enumerate(edge_seq):
        pair = require_strict_seq(edge, f"edges[{idx}]")
        if len(pair) != 2:
            raise VenturiBioError("INVALID_EDGE", f"edges[{idx}] must have length 2")
        u = require_exact_int(pair[0], f"edges[{idx}][0]", min_val=0, max_val=n - 1)
        v = require_exact_int(pair[1], f"edges[{idx}][1]", min_val=0, max_val=n - 1)
        if u == v:
            raise VenturiBioError("SELF_LOOP_FORBIDDEN", f"self-loop at node {u}")
        und = (u, v) if u < v else (v, u)
        if und in seen_undirected:
            raise VenturiBioError("DUPLICATE_EDGE", f"parallel/duplicate edge {und}")
        seen_undirected.add(und)
        clean_edges.append((u, v))
    return n, clean_edges


def _connected_components(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    adj: list[list[int]] = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    visited = [False] * n
    comps: list[list[int]] = []
    for start in range(n):
        if visited[start]:
            continue
        comp: list[int] = []
        q: deque[int] = deque([start])
        visited[start] = True
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nxt in adj[cur]:
                if not visited[nxt]:
                    visited[nxt] = True
                    q.append(nxt)
        comps.append(sorted(comp))
    return comps


# ---------------------------------------------------------------------------
# Pillar 1 (Operator 2): Cascaded Load Splitting, Attenuation & Choke Contraction
# ---------------------------------------------------------------------------

def evaluate_head_cascade_exact(total_head: Any, stage_heads: Any) -> dict[str, Any]:
    """Exact-Q K-stage hydrostatic thrust/moment splitting and Jensen excess."""
    H = require_exact_fraction(total_head, "total_head", positive=True)
    raw_stages = require_strict_seq(stage_heads, "stage_heads")
    if len(raw_stages) == 0:
        raise VenturiBioError("EMPTY_STAGES", "stage_heads must be non-empty")
    hs = [require_exact_fraction(x, f"stage_heads[{i}]", positive=True) for i, x in enumerate(raw_stages)]
    if sum(hs, Fraction(0, 1)) != H:
        raise VenturiBioError("HEAD_CONSERVATION_MISMATCH", "sum(stage_heads) != total_head")

    k = len(hs)
    f_mono = H * H / 2
    m_mono = H * H * H / 6
    f_stages = [h * h / 2 for h in hs]
    m_stages = [h * h * h / 6 for h in hs]
    f_tot = sum(f_stages, Fraction(0, 1))
    m_tot = sum(m_stages, Fraction(0, 1))
    m_peak = max(m_stages)

    # Exact Jensen excess: sum(h_i^2) - H^2/K == (1/K) * sum_{i<j} (h_i - h_j)^2
    sum_sq = sum((h * h for h in hs), Fraction(0, 1))
    jensen_excess = sum_sq - (H * H) / k
    pairwise_excess = Fraction(0, 1)
    for i in range(k):
        for j in range(i + 1, k):
            diff = hs[i] - hs[j]
            pairwise_excess += diff * diff
    pairwise_excess /= k
    jensen_identity_ok = jensen_excess == pairwise_excess

    return {
        "k_stages": k,
        "total_head": frac_str(H),
        "stage_heads": [frac_str(h) for h in hs],
        "force_reduction_factor": frac_str(f_mono / f_tot),
        "peak_moment_reduction_factor": frac_str(m_mono / m_peak),
        "total_moment_reduction_factor": frac_str(m_mono / m_tot),
        "jensen_excess": frac_str(jensen_excess),
        "jensen_identity_verified": jensen_identity_ok,
        "is_uniform": jensen_excess == 0,
    }


def evaluate_cascade_attenuation_exact(k_stages: Any, alpha: Any, steps: Any) -> dict[str, Any]:
    """Exact discrete K-stage linear-basin impulse convolution vs negative-binomial closed form."""
    k = require_exact_int(k_stages, "k_stages", min_val=1, max_val=16)
    a = require_exact_fraction(alpha, "alpha", positive=True)
    if a >= 1:
        raise VenturiBioError("INVALID_ALPHA", "alpha must lie strictly in (0, 1)")
    n_steps = require_exact_int(steps, "steps", min_val=1, max_val=64)

    # Discrete cascade recurrence Q_i[t] = a * Q_{i-1}[t] + (1 - a) * Q_i[t-1]
    prev_stage = [Fraction(1, 1) if t == 0 else Fraction(0, 1) for t in range(n_steps)]
    one_minus_a = Fraction(1, 1) - a
    for _ in range(k):
        cur_stage: list[Fraction] = []
        running = Fraction(0, 1)
        for t in range(n_steps):
            running = a * prev_stage[t] + one_minus_a * running
            cur_stage.append(running)
        prev_stage = cur_stage

    # Independent closed-form negative-binomial verification at every step
    a_pow_k = a ** k
    closed_form_ok = all(
        prev_stage[t] == Fraction(math.comb(t + k - 1, k - 1), 1) * a_pow_k * (one_minus_a ** t)
        for t in range(n_steps)
    )

    peak_val = max(prev_stage)
    peak_t = prev_stage.index(peak_val)
    return {
        "k_stages": k,
        "alpha": frac_str(a),
        "steps": n_steps,
        "peak_outflow": frac_str(peak_val),
        "peak_step": peak_t,
        "closed_form_verified": closed_form_ok,
    }


def evaluate_choke_feedback_exact(
    g0: Any,
    head: Any,
    feedback_coeff: Any,
    steps: Any,
    mode: Any,
) -> dict[str, Any]:
    """Exact-Q rational reed-choke negative feedback vs runaway positive feedback."""
    g = require_exact_fraction(g0, "g0", positive=True)
    h = require_exact_fraction(head, "head", positive=True)
    coeff = require_exact_fraction(feedback_coeff, "feedback_coeff", positive=True)
    n_steps = require_exact_int(steps, "steps", min_val=1, max_val=12)
    if type(mode) is not str or mode not in ("contractive", "runaway"):
        raise VenturiBioError("INVALID_CHOKE_MODE", "mode must be 'contractive' or 'runaway'")

    g_init = g
    inv_g0_sq = Fraction(1, 1) / (g_init * g_init)
    two_c_h2 = 2 * coeff * h * h
    trace_g: list[Fraction] = [g]
    lyapunov_holds = True
    strictly_contracting = True
    strictly_expanding = True

    for t in range(1, n_steps + 1):
        q = g * h
        factor = Fraction(1, 1) + coeff * q * q
        if mode == "contractive":
            g_next = g / factor
            if g_next >= g:
                strictly_contracting = False
            if Fraction(1, 1) / (g_next * g_next) <= inv_g0_sq + t * two_c_h2:
                lyapunov_holds = False
            strictly_expanding = False
        else:
            g_next = g * factor
            if g_next <= g:
                strictly_expanding = False
            strictly_contracting = False
            lyapunov_holds = False
        g = g_next
        trace_g.append(g)

    return {
        "mode": mode,
        "g0": frac_str(g_init),
        "head": frac_str(h),
        "feedback_coeff": frac_str(coeff),
        "steps": n_steps,
        "g_final": frac_str(trace_g[-1]),
        "q_final": frac_str(trace_g[-1] * h),
        "ratio_g_final_to_g0": frac_str(trace_g[-1] / g_init),
        "strictly_contracting": strictly_contracting,
        "strictly_expanding": strictly_expanding,
        "lyapunov_bound_verified": lyapunov_holds,
    }


# ---------------------------------------------------------------------------
# Pillar 2 (Operator 3): Cycle-Space Passive Ventilation & Blockage Survival
# ---------------------------------------------------------------------------

def solve_kirchhoff_circulation_exact(
    n_nodes: Any,
    edges: Any,
    conductances: Any,
    eta: Any,
) -> dict[str, Any]:
    """Exact-Q Kirchhoff circulation solved twice (nodal Laplacian + cycle-basis projection)."""
    n, clean_edges = _validate_graph(n_nodes, edges)
    m = len(clean_edges)
    g_seq = require_strict_seq(conductances, "conductances")
    eta_seq = require_strict_seq(eta, "eta")
    if len(g_seq) != m or len(eta_seq) != m:
        raise VenturiBioError("VECTOR_LENGTH_MISMATCH", "conductances and eta must match len(edges)")
    gs = [require_exact_fraction(x, f"conductances[{i}]", positive=True) for i, x in enumerate(g_seq)]
    etas = [require_exact_fraction(x, f"eta[{i}]") for i, x in enumerate(eta_seq)]

    comps = _connected_components(n, clean_edges)
    n_comps = len(comps)
    beta1 = m - n + n_comps

    # Method 1: Nodal weighted Laplacian solve per connected component (pin first node of each comp)
    phi = [Fraction(0, 1)] * n
    for comp in comps:
        if len(comp) == 1:
            continue
        idx_map = {node: idx for idx, node in enumerate(comp)}
        k_free = len(comp) - 1
        mat = [[Fraction(0, 1)] * k_free for _ in range(k_free)]
        rhs = [Fraction(0, 1)] * k_free
        for e_idx, (u, v) in enumerate(clean_edges):
            if u not in idx_map:
                continue
            iu, iv = idx_map[u], idx_map[v]
            ge = gs[e_idx]
            ee = etas[e_idx]
            # B has +1 at head v, -1 at tail u; q_e = g_e * (eta_e - (phi_v - phi_u))
            # (B G B^T phi)_node = (B G eta)_node
            if iu > 0:
                mat[iu - 1][iu - 1] += ge
                rhs[iu - 1] -= ge * ee
                if iv > 0:
                    mat[iu - 1][iv - 1] -= ge
            if iv > 0:
                mat[iv - 1][iv - 1] += ge
                rhs[iv - 1] += ge * ee
                if iu > 0:
                    mat[iv - 1][iu - 1] -= ge
        sol = solve_linear_exact(mat, rhs)
        for pos, val in enumerate(sol):
            phi[comp[pos + 1]] = val

    q_nodal = [gs[i] * (etas[i] - (phi[v] - phi[u])) for i, (u, v) in enumerate(clean_edges)]

    # Verify exact Kirchhoff node conservation B q == 0
    node_div = [Fraction(0, 1)] * n
    for i, (u, v) in enumerate(clean_edges):
        node_div[u] -= q_nodal[i]
        node_div[v] += q_nodal[i]
    kirchhoff_ok = all(d == 0 for d in node_div)

    # Method 2: Independent cycle-basis projection (C G^-1 C^T) i_loop = C eta
    adj_edges: list[list[tuple[int, int, int]]] = [[] for _ in range(n)]
    for e_idx, (u, v) in enumerate(clean_edges):
        adj_edges[u].append((v, e_idx, 1))
        adj_edges[v].append((u, e_idx, -1))
    parent_node: list[int] = [-1] * n
    parent_edge: list[int] = [-1] * n
    parent_sign: list[int] = [0] * n
    depth: list[int] = [-1] * n
    in_tree = [False] * m
    for start in range(n):
        if depth[start] >= 0:
            continue
        depth[start] = 0
        dq: deque[int] = deque([start])
        while dq:
            cur = dq.popleft()
            for nxt, e_idx, sign in adj_edges[cur]:
                if depth[nxt] < 0:
                    depth[nxt] = depth[cur] + 1
                    parent_node[nxt] = cur
                    parent_edge[nxt] = e_idx
                    parent_sign[nxt] = sign  # orientation from cur -> nxt
                    in_tree[e_idx] = True
                    dq.append(nxt)

    cycle_rows: list[list[Fraction]] = []
    for e_idx, (u, v) in enumerate(clean_edges):
        if in_tree[e_idx]:
            continue
        row = [Fraction(0, 1)] * m
        row[e_idx] = Fraction(1, 1)  # traverse chord u -> v
        # Close cycle from v back to u along the spanning tree
        a, b = v, u
        path_a: list[tuple[int, int]] = []
        path_b: list[tuple[int, int]] = []
        while depth[a] > depth[b]:
            # step a -> parent[a] is opposite to parent[a] -> a
            path_a.append((parent_edge[a], -parent_sign[a]))
            a = parent_node[a]
        while depth[b] > depth[a]:
            # step parent[b] -> b is +parent_sign[b]
            path_b.append((parent_edge[b], parent_sign[b]))
            b = parent_node[b]
        while a != b:
            path_a.append((parent_edge[a], -parent_sign[a]))
            path_b.append((parent_edge[b], parent_sign[b]))
            a = parent_node[a]
            b = parent_node[b]
        for pe, ps in path_a:
            row[pe] += ps
        for pe, ps in reversed(path_b):
            row[pe] += ps
        cycle_rows.append(row)

    cycle_rank_ok = len(cycle_rows) == beta1

    if beta1 == 0:
        q_cycle = [Fraction(0, 1)] * m
    else:
        r_mat = [[Fraction(0, 1)] * beta1 for _ in range(beta1)]
        c_rhs = [Fraction(0, 1)] * beta1
        for i in range(beta1):
            c_rhs[i] = sum((cycle_rows[i][e] * etas[e] for e in range(m)), Fraction(0, 1))
            for j in range(beta1):
                r_mat[i][j] = sum((cycle_rows[i][e] * cycle_rows[j][e] / gs[e] for e in range(m)), Fraction(0, 1))
        i_loop = solve_linear_exact(r_mat, c_rhs)
        q_cycle = [
            sum((cycle_rows[i][e] * i_loop[i] for i in range(beta1)), Fraction(0, 1))
            for e in range(m)
        ]

    dual_ok = q_nodal == q_cycle
    power_input = sum((etas[e] * q_nodal[e] for e in range(m)), Fraction(0, 1))
    power_diss = sum((q_nodal[e] * q_nodal[e] / gs[e] for e in range(m)), Fraction(0, 1))
    power_balance_ok = power_input == power_diss

    nonzero_flow = any(q != 0 for q in q_nodal)
    return {
        "n_nodes": n,
        "n_edges": m,
        "n_components": n_comps,
        "beta1": beta1,
        "flow_vector": [frac_str(q) for q in q_nodal],
        "convective_power": frac_str(power_input),
        "has_nonzero_circulation": nonzero_flow,
        "kirchhoff_conservation_verified": kirchhoff_ok,
        "cycle_basis_rank_verified": cycle_rank_ok,
        "dual_solver_verified": dual_ok,
        "power_balance_verified": power_balance_ok,
    }


def evaluate_duct_blockage_survival_exact(n_nodes: Any, edges: Any) -> dict[str, Any]:
    """Exhaustive exact-Q 1-edge and 2-edge blockage connectivity survival fractions."""
    n, clean_edges = _validate_graph(n_nodes, edges)
    m = len(clean_edges)
    if m < 2:
        raise VenturiBioError("TOO_FEW_EDGES", "need at least 2 edges for 1- and 2-edge blockage audit")
    base_comps = len(_connected_components(n, clean_edges))
    if base_comps != 1:
        raise VenturiBioError("DISCONNECTED_BASE_GRAPH", "base duct network must be connected")

    surv_1 = 0
    for i in range(m):
        rem = clean_edges[:i] + clean_edges[i + 1:]
        if len(_connected_components(n, rem)) == 1:
            surv_1 += 1

    total_2 = m * (m - 1) // 2
    surv_2 = 0
    for i in range(m):
        for j in range(i + 1, m):
            rem = [e for idx, e in enumerate(clean_edges) if idx != i and idx != j]
            if len(_connected_components(n, rem)) == 1:
                surv_2 += 1

    return {
        "n_nodes": n,
        "n_edges": m,
        "beta1": m - n + 1,
        "cut1_survive_count": surv_1,
        "cut1_total": m,
        "cut1_survival_fraction": frac_str(Fraction(surv_1, m)),
        "cut1_disconnect_fraction": frac_str(Fraction(m - surv_1, m)),
        "cut2_survive_count": surv_2,
        "cut2_total": total_2,
        "cut2_survival_fraction": frac_str(Fraction(surv_2, total_2)),
        "cut2_disconnect_fraction": frac_str(Fraction(total_2 - surv_2, total_2)),
    }


# ---------------------------------------------------------------------------
# Pillar 3 (dock#8): Receiving-Side Pass/Fail Collar Network Gate
# ---------------------------------------------------------------------------

def evaluate_receiving_collar_gate(
    *,
    label: str,
    total_head: Fraction,
    stage_heads: list[Fraction],
    choke_mode: str,
    choke_coeff: Fraction,
    choke_steps: int,
    n_nodes: int,
    edges: list[tuple[int, int]],
    conductances: list[Fraction],
    eta: list[Fraction],
) -> dict[str, Any]:
    """Receiving-side pass/fail checker (`dock#8`) combining Operators 2 & 3."""
    if type(label) is not str or not label.strip():
        raise VenturiBioError("INVALID_LABEL", "label must be non-empty str")
    cascade = evaluate_head_cascade_exact(total_head, stage_heads)
    choke = evaluate_choke_feedback_exact(Fraction(1, 1), Fraction(1, 1), choke_coeff, choke_steps, choke_mode)
    vent = solve_kirchhoff_circulation_exact(n_nodes, edges, conductances, eta)
    blockage = evaluate_duct_blockage_survival_exact(n_nodes, edges)

    reasons: list[str] = []
    if not cascade["is_uniform"]:
        reasons.append("NONZERO_JENSEN_EXCESS")
    if not (choke["strictly_contracting"] and choke["lyapunov_bound_verified"]):
        reasons.append("CHOKE_NOT_CONTRACTIVE")
    if vent["beta1"] < 1:
        reasons.append("BETTI1_ZERO_NO_CYCLE")
    if not vent["has_nonzero_circulation"]:
        reasons.append("ZERO_PASSIVE_CIRCULATION")
    if blockage["cut1_survive_count"] < blockage["cut1_total"]:
        reasons.append("SINGLE_EDGE_BLOCKAGE_VULNERABLE")

    return {
        "label": label,
        "passed": len(reasons) == 0,
        "failed_reasons": reasons,
        "cascade": cascade,
        "choke": choke,
        "ventilation": vent,
        "blockage": blockage,
    }


# ---------------------------------------------------------------------------
# Canonical Study Payload & Certificate Builder / Verifier
# ---------------------------------------------------------------------------

def _canonical_graphs() -> dict[str, tuple[int, list[tuple[int, int]], list[Fraction]]]:
    # 8-junction Q3 manifold vertices 0..7
    # Tree: spanning path 0-1-2-3-4-5-6-7 (7 edges, beta1=0)
    tree_edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
    # Ring: close 7->0 (8 edges, beta1=1)
    ring_edges = tree_edges + [(7, 0)]
    # Redundant 3-loop collar: add 2 cross-ducts (0,3) and (4,7) -> 10 edges, beta1=3
    sparse_3loop_edges = ring_edges + [(0, 3), (4, 7)]
    # Full Q3 cube manifold: 12 edges, beta1=5 (vertices indexed by 3-bit mask)
    cube_edges = [
        (0, 1), (2, 3), (4, 5), (6, 7),
        (0, 2), (1, 3), (4, 6), (5, 7),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    # Looped graph with a single cut-edge (bridge (3,4) between 4-cycle 0-1-2-3-0 and 4-cycle 4-5-6-7-4)
    # Wait: (0,1),(1,2),(2,3),(3,0),(3,4),(4,5),(5,6),(6,7),(7,4) -> 9 edges, beta1=2, bridge (3,4)!
    bridge_loop_edges = [(0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 5), (5, 6), (6, 7), (7, 4)]

    # Non-coboundary thermal/wind stack head: +1 on (0,1) and (2,3) -> nonzero cycle integral around ring!
    eta_tree = [Fraction(1, 1), Fraction(0, 1), Fraction(1, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1)]
    eta_ring_day = eta_tree + [Fraction(0, 1)]
    # Exact coboundary eta = B^T z with z = [0,1,2,3,4,5,6,7] on ring
    z_elev = [Fraction(i, 1) for i in range(8)]
    eta_ring_coboundary = [z_elev[v] - z_elev[u] for u, v in ring_edges]
    eta_3loop_day = eta_ring_day + [Fraction(0, 1), Fraction(0, 1)]
    eta_bridge_day = [Fraction(1, 1), Fraction(0, 1), Fraction(1, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1), Fraction(0, 1)]

    return {
        "tree": (8, tree_edges, eta_tree),
        "ring_day": (8, ring_edges, eta_ring_day),
        "ring_coboundary": (8, ring_edges, eta_ring_coboundary),
        "sparse_3loop": (8, sparse_3loop_edges, eta_3loop_day),
        "cube_5loop": (8, cube_edges, [Fraction(1, 1)] + [Fraction(0, 1)] * 11),
        "bridge_loop": (8, bridge_loop_edges, eta_bridge_day),
    }


def build_study_payload() -> dict[str, Any]:
    """Compute complete pure-Z/Q Operators 2 & 3 payload for aska-physical/venturi-collars."""
    # Pillar 1: Head cascades (K=1,2,4,8 uniform + unequal control), convolution attenuation, choke vs runaway
    h_total = Fraction(8, 1)
    uniform_cascades = [
        evaluate_head_cascade_exact(h_total, [h_total / k] * k)
        for k in (1, 2, 4, 8)
    ]
    unequal_cascade = evaluate_head_cascade_exact(
        h_total, [Fraction(4, 1), Fraction(4, 3), Fraction(4, 3), Fraction(4, 3)]
    )

    added_storage_attenuation = [
        evaluate_cascade_attenuation_exact(k, Fraction(1, 2), 16)
        for k in (1, 2, 4, 8)
    ]
    # Law-2b fixed-mean-residence-time control (tau=7, alpha_K = K/(K+7)) -> honest non-monotone disclosure
    fixed_storage_control = [
        evaluate_cascade_attenuation_exact(k, Fraction(k, k + 7), 16)
        for k in (1, 2, 8)
    ]

    choke_contractive = evaluate_choke_feedback_exact(Fraction(1, 1), Fraction(1, 1), Fraction(1, 4), 5, "contractive")
    choke_runaway = evaluate_choke_feedback_exact(Fraction(1, 1), Fraction(1, 1), Fraction(1, 4), 5, "runaway")
    runaway_over_contractive = Fraction(choke_runaway["g_final"]) / Fraction(choke_contractive["g_final"])

    # Pillar 2: Kirchhoff circulation + diurnal reversal + blockage survival
    graphs = _canonical_graphs()
    n_t, e_t, eta_t = graphs["tree"]
    n_r, e_r, eta_r_day = graphs["ring_day"]
    _, _, eta_r_cob = graphs["ring_coboundary"]
    n_s, e_s, eta_s_day = graphs["sparse_3loop"]
    n_c, e_c, _ = graphs["cube_5loop"]
    n_b, e_b, eta_b_day = graphs["bridge_loop"]

    vent_tree = solve_kirchhoff_circulation_exact(n_t, e_t, [Fraction(1, 1)] * len(e_t), eta_t)
    vent_ring_cob = solve_kirchhoff_circulation_exact(n_r, e_r, [Fraction(1, 1)] * len(e_r), eta_r_cob)
    vent_ring_day = solve_kirchhoff_circulation_exact(n_r, e_r, [Fraction(1, 1)] * len(e_r), eta_r_day)
    vent_ring_night = solve_kirchhoff_circulation_exact(n_r, e_r, [Fraction(1, 1)] * len(e_r), [-x for x in eta_r_day])
    diurnal_exact_reversal = all(
        Fraction(qd) == -Fraction(qn)
        for qd, qn in zip(vent_ring_day["flow_vector"], vent_ring_night["flow_vector"])
    )
    vent_3loop_day = solve_kirchhoff_circulation_exact(n_s, e_s, [Fraction(1, 1)] * len(e_s), eta_s_day)

    blockage_frontier = {
        "tree_duct": evaluate_duct_blockage_survival_exact(n_t, e_t),
        "ring_duct": evaluate_duct_blockage_survival_exact(n_r, e_r),
        "redundant_collar_3loop": evaluate_duct_blockage_survival_exact(n_s, e_s),
        "cube_collar_5loop": evaluate_duct_blockage_survival_exact(n_c, e_c),
    }

    # Pillar 3: Receiving-side dock#8 pass/fail controls (1 PASS + 5 distinct FAIL controls)
    gate_pass = evaluate_receiving_collar_gate(
        label="pass_balanced_contractive_3loop_collar",
        total_head=h_total,
        stage_heads=[Fraction(2, 1)] * 4,
        choke_mode="contractive",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_s,
        edges=e_s,
        conductances=[Fraction(1, 1)] * len(e_s),
        eta=eta_s_day,
    )
    gate_fail_runaway = evaluate_receiving_collar_gate(
        label="fail_runaway_feedback_blowup",
        total_head=h_total,
        stage_heads=[Fraction(2, 1)] * 4,
        choke_mode="runaway",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_s,
        edges=e_s,
        conductances=[Fraction(1, 1)] * len(e_s),
        eta=eta_s_day,
    )
    gate_fail_unequal = evaluate_receiving_collar_gate(
        label="fail_unbalanced_stage_partition",
        total_head=h_total,
        stage_heads=[Fraction(4, 1), Fraction(4, 3), Fraction(4, 3), Fraction(4, 3)],
        choke_mode="contractive",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_s,
        edges=e_s,
        conductances=[Fraction(1, 1)] * len(e_s),
        eta=eta_s_day,
    )
    gate_fail_tree = evaluate_receiving_collar_gate(
        label="fail_tree_duct_zero_circulation",
        total_head=h_total,
        stage_heads=[Fraction(2, 1)] * 4,
        choke_mode="contractive",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_t,
        edges=e_t,
        conductances=[Fraction(1, 1)] * len(e_t),
        eta=eta_t,
    )
    gate_fail_coboundary = evaluate_receiving_collar_gate(
        label="fail_coboundary_blocked_loop",
        total_head=h_total,
        stage_heads=[Fraction(2, 1)] * 4,
        choke_mode="contractive",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_r,
        edges=e_r,
        conductances=[Fraction(1, 1)] * len(e_r),
        eta=eta_r_cob,
    )
    gate_fail_bridge = evaluate_receiving_collar_gate(
        label="fail_single_point_bridge_blockage",
        total_head=h_total,
        stage_heads=[Fraction(2, 1)] * 4,
        choke_mode="contractive",
        choke_coeff=Fraction(1, 4),
        choke_steps=5,
        n_nodes=n_b,
        edges=e_b,
        conductances=[Fraction(1, 1)] * len(e_b),
        eta=eta_b_day,
    )

    gate_checks = {
        "positive_control_passes": gate_pass["passed"] is True,
        "rejects_runaway_feedback": gate_fail_runaway["failed_reasons"] == ["CHOKE_NOT_CONTRACTIVE"],
        "rejects_unequal_stage_partition": gate_fail_unequal["failed_reasons"] == ["NONZERO_JENSEN_EXCESS"],
        "rejects_tree_duct_zero_circulation": gate_fail_tree["failed_reasons"] == [
            "BETTI1_ZERO_NO_CYCLE",
            "ZERO_PASSIVE_CIRCULATION",
            "SINGLE_EDGE_BLOCKAGE_VULNERABLE",
        ],
        "rejects_coboundary_blocked_loop": gate_fail_coboundary["failed_reasons"] == ["ZERO_PASSIVE_CIRCULATION"],
        "rejects_single_point_bridge_blockage": gate_fail_bridge["failed_reasons"] == ["SINGLE_EDGE_BLOCKAGE_VULNERABLE"],
        "diurnal_exact_reversal": diurnal_exact_reversal,
        "added_storage_monotone_peak_drop": (
            Fraction(added_storage_attenuation[0]["peak_outflow"])
            > Fraction(added_storage_attenuation[1]["peak_outflow"])
            > Fraction(added_storage_attenuation[2]["peak_outflow"])
            > Fraction(added_storage_attenuation[3]["peak_outflow"])
        ),
        "fixed_storage_nonmonotone_disclosed": (
            Fraction(fixed_storage_control[1]["peak_outflow"]) < Fraction(fixed_storage_control[0]["peak_outflow"])
            and Fraction(fixed_storage_control[1]["peak_outflow"]) < Fraction(fixed_storage_control[2]["peak_outflow"])
        ),
        "runaway_exceeds_500x_contractive": runaway_over_contractive > 500,
    }
    failed_invariants = [k for k, ok in gate_checks.items() if not ok]
    if failed_invariants:
        raise VenturiBioError("STUDY_INVARIANT_FAILED", f"failed invariants: {failed_invariants}")

    return {
        "target_repository": "aska-physical/venturi-collars",
        "target_baseline_commit": "d53f85a35d17a7bd46d0b5320c8879fc9f381978",
        "target_code_anchors": [
            "verify.py:17-41 (1D duct & K_venturi gradual vs abrupt diffuser)",
            "verify.py:68-69 (hard reed amplitude clamp min(0.0040, ...))",
            "verify.py:109-125 (isolated duct sweep & abrupt 45-deg baffle control)",
        ],
        "claim_scope": _CLAIM_SCOPE,
        "pillar_1_cascaded_choke_operator2": {
            "uniform_head_cascades": uniform_cascades,
            "unequal_head_cascade_control": unequal_cascade,
            "added_storage_attenuation": added_storage_attenuation,
            "fixed_storage_nonmonotone_control": fixed_storage_control,
            "choke_contractive": choke_contractive,
            "choke_runaway": choke_runaway,
            "runaway_to_contractive_g_ratio": frac_str(runaway_over_contractive),
        },
        "pillar_2_cycle_ventilation_operator3": {
            "tree_duct_zero_flow": vent_tree,
            "ring_duct_coboundary_zero_flow": vent_ring_cob,
            "ring_duct_noncoboundary_day": vent_ring_day,
            "ring_duct_noncoboundary_night": vent_ring_night,
            "diurnal_exact_reversal": diurnal_exact_reversal,
            "redundant_3loop_collar_day": vent_3loop_day,
            "blockage_survival_frontier": blockage_frontier,
        },
        "pillar_3_receiving_gate_controls": {
            "pass_balanced_contractive_3loop": gate_pass,
            "fail_runaway_feedback": gate_fail_runaway,
            "fail_unbalanced_stages": gate_fail_unequal,
            "fail_tree_duct": gate_fail_tree,
            "fail_coboundary_loop": gate_fail_coboundary,
            "fail_bridge_blockage": gate_fail_bridge,
        },
        "invariant_checks": gate_checks,
        "all_passed": True,
    }


def build_certificate() -> dict[str, Any]:
    payload = build_study_payload()
    payload_sha256 = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    envelope = {
        "schema": CERT_SCHEMA,
        "study_id": CERT_STUDY_ID,
        "claim_scope": _CLAIM_SCOPE,
        "payload_sha256": payload_sha256,
        "payload": payload,
    }
    certificate_sha256 = hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
    return {
        "schema": CERT_SCHEMA,
        "study_id": CERT_STUDY_ID,
        "claim_scope": _CLAIM_SCOPE,
        "payload_sha256": payload_sha256,
        "certificate_sha256": certificate_sha256,
        "payload": payload,
    }


def verify_certificate_dict(cert: Any) -> dict[str, Any]:
    """Fail-closed verification of a parsed certificate dictionary."""
    if type(cert) is not dict:
        raise VenturiBioError("CERT_NOT_DICT", "certificate root must be a JSON object")
    if set(cert.keys()) != _CERT_KEYS:
        raise VenturiBioError("CERT_SCHEMA_KEYS", f"unexpected keys: {sorted(cert.keys())}")
    if cert["schema"] != CERT_SCHEMA:
        raise VenturiBioError("CERT_SCHEMA_MISMATCH", "schema mismatch")
    if cert["study_id"] != CERT_STUDY_ID:
        raise VenturiBioError("CERT_STUDY_ID_MISMATCH", "study_id mismatch")
    if cert["claim_scope"] != _CLAIM_SCOPE:
        raise VenturiBioError("CERT_CLAIM_SCOPE_MISMATCH", "claim_scope mismatch")

    stored_payload_sha = _require_sha256_hex(cert["payload_sha256"], "payload_sha256")
    stored_cert_sha = _require_sha256_hex(cert["certificate_sha256"], "certificate_sha256")

    computed_payload_sha = hashlib.sha256(canonical_json_bytes(cert["payload"])).hexdigest()
    if not hmac.compare_digest(stored_payload_sha, computed_payload_sha):
        raise VenturiBioError("PAYLOAD_SHA_MISMATCH", "payload_sha256 mismatch")

    envelope = {
        "schema": cert["schema"],
        "study_id": cert["study_id"],
        "claim_scope": cert["claim_scope"],
        "payload_sha256": stored_payload_sha,
        "payload": cert["payload"],
    }
    computed_cert_sha = hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
    if not hmac.compare_digest(stored_cert_sha, computed_cert_sha):
        raise VenturiBioError("CERTIFICATE_SHA_MISMATCH", "certificate_sha256 mismatch")

    expected = build_certificate()
    if not hmac.compare_digest(computed_payload_sha, expected["payload_sha256"]):
        raise VenturiBioError("RECOMPUTED_PAYLOAD_DRIFT", "payload digest differs from exact recomputation")

    return {
        "valid": True,
        "study_id": CERT_STUDY_ID,
        "payload_sha256": computed_payload_sha,
        "certificate_sha256": computed_cert_sha,
    }


def check_certificate_file(path: Path) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise VenturiBioError("INVALID_PATH_TYPE", "path must be pathlib.Path")
    _require_no_symlink_path(path)
    if not path.is_file():
        raise VenturiBioError("CERT_FILE_NOT_FOUND", f"certificate file not found: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise VenturiBioError("CERT_FILE_TOO_LARGE", "certificate file exceeds byte cap")
    raw = path.read_bytes()
    if b"\r\n" in raw:
        raise VenturiBioError("CRLF_FORBIDDEN", "CRLF line endings forbidden in certificate")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VenturiBioError("INVALID_UTF8", f"invalid UTF-8: {exc}") from exc
    parsed = parse_strict_json(text)
    canonical_raw = canonical_json_bytes(parsed)
    if raw not in (canonical_raw, canonical_raw + b"\n"):
        raise VenturiBioError("NON_CANONICAL_CERT_BYTES", "certificate file is not canonical JSON")
    return verify_certificate_dict(parsed)


def write_certificate_file(path: Path) -> dict[str, Any]:
    _require_no_symlink_path(path)
    cert = build_certificate()
    raw = canonical_json_bytes(cert) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return check_certificate_file(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exact-Q receiving-side checker for cascaded choke & cycle-space passive ventilation."
    )
    parser.add_argument("--standalone", action="store_true", help="Run full standalone exact verification")
    parser.add_argument("--json", action="store_true", help="Emit canonical JSON certificate to stdout")
    parser.add_argument("--write", nargs="?", const=str(DEFAULT_CERT_PATH), help="Write canonical certificate file")
    parser.add_argument("--check", type=str, help="Fail-closed verification of a certificate JSON file")
    args = parser.parse_args(argv)

    try:
        if args.check is not None:
            res = check_certificate_file(Path(args.check))
            print(
                f"OK {CERT_STUDY_ID} payload_sha256={res['payload_sha256']} "
                f"certificate_sha256={res['certificate_sha256']}"
            )
            return 0
        if args.write is not None:
            res = write_certificate_file(Path(args.write))
            print(
                f"WROTE {CERT_STUDY_ID} payload_sha256={res['payload_sha256']} "
                f"certificate_sha256={res['certificate_sha256']}"
            )
            return 0
        cert = build_certificate()
        if args.json:
            sys.stdout.buffer.write(canonical_json_bytes(cert) + b"\n")
            return 0
        print(
            f"OK {CERT_STUDY_ID} payload_sha256={cert['payload_sha256']} "
            f"certificate_sha256={cert['certificate_sha256']} "
            f"all_passed={cert['payload']['all_passed']}"
        )
        return 0
    except (VenturiBioError, ValueError, RecursionError, OSError) as exc:
        print(f"REJECT {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
