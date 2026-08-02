from pathlib import Path
import math
import random
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
SETMAT_SOURCE = REPO_ROOT / "Soil Source" / "SETMAT01.FOR"

HUTD06_PARAMETERS = (
    (0.0422, 0.3428, 0.0422, 0.3484, 0.04077, 1.45476, 31.983, 28.7849, 0.3388),
    (0.0483, 0.3143, 0.0483, 0.3176, 0.03435, 1.18822, 3.638, 3.2739, 0.3103),
    (0.0525, 0.3677, 0.0525, 0.3711, 0.02641, 1.34642, 15.594, 14.0344, 0.3637),
    (0.0676, 0.3444, 0.0676, 0.3463, 0.01905, 1.22181, 1.518, 1.3660, 0.3404),
    (0.0642, 0.3223, 0.0642, 0.3240, 0.01969, 1.20308, 0.943, 0.8483, 0.3183),
    (0.0554, 0.3076, 0.0554, 0.3094, 0.02002, 1.21481, 1.020, 0.9181, 0.3036),
    (0.0677, 0.3365, 0.0677, 0.3381, 0.01751, 1.22783, 1.166, 1.0495, 0.3325),
)


def _branch_points(parameters):
    _, theta_s, theta_a, theta_m, alpha, exponent_n, _, _, theta_k = parameters
    exponent_m = 1.0 - 1.0 / exponent_n
    effective_s = min(
        (theta_s - theta_a) / (theta_m - theta_a),
        0.999999999999999,
    )
    effective_k = min(
        (theta_k - theta_a) / (theta_m - theta_a),
        effective_s,
    )
    h_s = -(effective_s ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    h_k = -(effective_k ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    return h_k, h_s


def _legacy_fk(h, parameters):
    _, theta_s, theta_a, theta_m, alpha, exponent_n, k_s, k_k, theta_k = (
        parameters
    )
    exponent_m = 1.0 - 1.0 / exponent_n
    h_min = -(1.0e300 ** (1.0 / exponent_n)) / max(alpha, 1.0)
    bounded_h = max(h, h_min)
    effective_s = min(
        (theta_s - theta_a) / (theta_m - theta_a),
        0.999999999999999,
    )
    effective_k = min(
        (theta_k - theta_a) / (theta_m - theta_a),
        effective_s,
    )
    h_s = -(effective_s ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    h_k = -(effective_k ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    if h < h_k:
        qee = (1.0 + (-alpha * bounded_h) ** exponent_n) ** (-exponent_m)
        qe = (theta_m - theta_a) / (theta_s - theta_a) * qee
        qek = (theta_m - theta_a) / (theta_s - theta_a) * effective_k
        ffq = 1.0 - (1.0 - qee ** (1.0 / exponent_m)) ** exponent_m
        ffqk = 1.0 - (1.0 - effective_k ** (1.0 / exponent_m)) ** exponent_m
        if ffq <= 0.0:
            ffq = exponent_m * qee ** (1.0 / exponent_m)
        relative_k = (
            (qe / qek) ** 0.5
            * (ffq / ffqk) ** 2.0
            * k_k
            / k_s
        )
        return max(k_s * relative_k, 1.0e-37)
    if h < h_s:
        relative_k = (1.0 - k_k / k_s) / (h_s - h_k) * (h - h_s) + 1.0
        return k_s * relative_k
    return k_s


def _legacy_fq(h, parameters):
    _, theta_s, theta_a, theta_m, alpha, exponent_n, *_ = parameters
    exponent_m = 1.0 - 1.0 / exponent_n
    h_min = -(1.0e300 ** (1.0 / exponent_n)) / max(alpha, 1.0)
    bounded_h = max(h, h_min)
    effective_s = min(
        (theta_s - theta_a) / (theta_m - theta_a),
        0.999999999999999,
    )
    h_s = -(effective_s ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    if h < h_s:
        qee = (1.0 + (-alpha * bounded_h) ** exponent_n) ** (-exponent_m)
        return max(theta_a + (theta_m - theta_a) * qee, 1.0e-37)
    return theta_s


def _current_properties(h, parameters):
    _, theta_s, theta_a, theta_m, alpha, exponent_n, k_s, k_k, theta_k = (
        parameters
    )
    exponent_m = 1.0 - 1.0 / exponent_n
    h_min = -(1.0e300 ** (1.0 / exponent_n)) / max(alpha, 1.0)
    bounded_h = max(h, h_min)
    effective_s = min(
        (theta_s - theta_a) / (theta_m - theta_a),
        0.999999999999999,
    )
    effective_k = min(
        (theta_k - theta_a) / (theta_m - theta_a),
        effective_s,
    )
    h_s = -(effective_s ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    h_k = -(effective_k ** (-1.0 / exponent_m) - 1.0) ** (
        1.0 / exponent_n
    ) / alpha
    power = (-alpha * bounded_h) ** exponent_n
    qee = (1.0 + power) ** (-exponent_m)
    dqee = 0.0
    if h > h_min:
        dqee = (
            exponent_m
            * exponent_n
            * alpha
            * (-alpha * bounded_h) ** (exponent_n - 1.0)
            * (1.0 + power) ** (-exponent_m - 1.0)
        )

    if h < h_s:
        raw_theta = theta_a + (theta_m - theta_a) * qee
        theta = max(raw_theta, 1.0e-37)
        dtheta = (theta_m - theta_a) * dqee if raw_theta > 1.0e-37 else 0.0
    else:
        theta = theta_s
        dtheta = 0.0

    if h < h_k:
        qe = (theta_m - theta_a) / (theta_s - theta_a) * qee
        qek = (theta_m - theta_a) / (theta_s - theta_a) * effective_k
        raw_ffq = 1.0 - (1.0 - qee ** (1.0 / exponent_m)) ** exponent_m
        ffqk = 1.0 - (1.0 - effective_k ** (1.0 / exponent_m)) ** exponent_m
        ffq = raw_ffq
        if ffq <= 0.0:
            ffq = exponent_m * qee ** (1.0 / exponent_m)
        relative_k = (
            (qe / qek) ** 0.5
            * (ffq / ffqk) ** 2.0
            * k_k
            / k_s
        )
        raw_k = k_s * relative_k
        conductivity = max(raw_k, 1.0e-37)
        dconductivity = 0.0
        if raw_k > 1.0e-37 and dqee > 0.0:
            dlog_qee = dqee / qee
            if raw_ffq > 0.0:
                dffq = (
                    (1.0 - qee ** (1.0 / exponent_m)) ** (exponent_m - 1.0)
                    * qee ** (1.0 / exponent_m - 1.0)
                    * dqee
                )
                dlog_ffq = dffq / ffq
            else:
                dlog_ffq = dlog_qee / exponent_m
            dconductivity = raw_k * (0.5 * dlog_qee + 2.0 * dlog_ffq)
    elif h < h_s:
        relative_k = (1.0 - k_k / k_s) / (h_s - h_k) * (h - h_s) + 1.0
        conductivity = k_s * relative_k
        dconductivity = (k_s - k_k) / (h_s - h_k)
    else:
        conductivity = k_s
        dconductivity = 0.0
    return conductivity, dconductivity, theta, dtheta


def _assert_derivative_matches(analytical, finite_difference):
    error = abs(analytical - finite_difference)
    scale = max(abs(analytical), abs(finite_difference))
    assert error <= 1.0e-12 + 1.0e-5 * scale


def _central_difference(function, h):
    step = 1.0e-6 * max(abs(h), 1.0)
    return (function(h + step) - function(h - step)) / (2.0 * step)


def test_setmat_current_point_contract_is_isolated_from_legacy_path():
    source = SETMAT_SOURCE.read_text(encoding="utf-8", errors="ignore")
    code = "\n".join(
        line for line in source.splitlines() if not line.lower().startswith("c")
    )
    compact = re.sub(r"[\s!&]+", "", code.lower())
    start = compact.index("subroutinesetmatcurrentpoint")
    end = compact.index("doubleprecisionfunctionfk", start)
    current_point = compact[start:end]

    assert "hnew" not in current_point
    assert "htemp" not in current_point
    assert "dcon=(ks-kk)/(hs-hk)" in current_point
    assert "dtheta=(qm-qa)*dqee" in current_point
    assert current_point.count("dcon=0.0d0") >= 2
    assert current_point.count("dtheta=0.0d0") >= 2
    assert "him=0.1*hi1+0.9*hi2" in compact[:start]
    assert "doubleprecisionfunctionfk(h,par)" in compact[end:]
    assert "doubleprecisionfunctionfc(h,par)" in compact[end:]
    assert "doubleprecisionfunctionfq(h,par)" in compact[end:]


def test_current_properties_match_legacy_values_and_are_finite_nonnegative():
    heads = (-1.0e6, -1.0e4, -1000.0, -100.0, -10.0, -1.0, 0.0, 10.0)
    for parameters in HUTD06_PARAMETERS:
        for h in heads:
            conductivity, dconductivity, theta, dtheta = _current_properties(
                h, parameters
            )
            assert conductivity == _legacy_fk(h, parameters)
            assert theta == _legacy_fq(h, parameters)
            assert all(
                math.isfinite(value)
                for value in (conductivity, dconductivity, theta, dtheta)
            )
            assert conductivity >= 0.0
            assert dconductivity >= 0.0
            assert theta >= 0.0
            assert dtheta >= 0.0


def test_random_nonbranch_derivatives_match_centered_finite_differences():
    rng = random.Random(20260731)
    for _ in range(120):
        parameters = rng.choice(HUTD06_PARAMETERS)
        h_k, h_s = _branch_points(parameters)
        branch = rng.randrange(3)
        if branch == 0:
            h = h_k * 10.0 ** rng.uniform(0.05, 3.0)
        elif branch == 1:
            h = h_k + rng.uniform(0.05, 0.95) * (h_s - h_k)
        else:
            h = h_s + rng.uniform(0.05, 2.0) * max(abs(h_s), 1.0)

        conductivity, dconductivity, theta, dtheta = _current_properties(
            h, parameters
        )
        finite_dk = _central_difference(
            lambda trial_h: _current_properties(trial_h, parameters)[0],
            h,
        )
        finite_dtheta = _central_difference(
            lambda trial_h: _current_properties(trial_h, parameters)[2],
            h,
        )
        _assert_derivative_matches(dconductivity, finite_dk)
        _assert_derivative_matches(dtheta, finite_dtheta)
        assert all(
            math.isfinite(value)
            for value in (conductivity, dconductivity, theta, dtheta)
        )


def test_hk_hs_use_consistent_one_sided_derivatives():
    for parameters in HUTD06_PARAMETERS:
        h_k, h_s = _branch_points(parameters)
        step_k = 1.0e-7 * max(abs(h_k), 1.0)
        step_s = 1.0e-7 * max(abs(h_s), 1.0)

        k_at_hk, dk_right, _, _ = _current_properties(h_k, parameters)
        k_after_hk = _current_properties(h_k + step_k, parameters)[0]
        _assert_derivative_matches(dk_right, (k_after_hk - k_at_hk) / step_k)

        dk_left = _current_properties(math.nextafter(h_k, -math.inf), parameters)[1]
        k_before_hk = _current_properties(h_k - step_k, parameters)[0]
        _assert_derivative_matches(dk_left, (k_at_hk - k_before_hk) / step_k)

        k_at_hs, dk_right, theta_at_hs, dtheta_right = _current_properties(
            h_s, parameters
        )
        k_after_hs, _, theta_after_hs, _ = _current_properties(
            h_s + step_s, parameters
        )
        _assert_derivative_matches(dk_right, (k_after_hs - k_at_hs) / step_s)
        _assert_derivative_matches(
            dtheta_right,
            (theta_after_hs - theta_at_hs) / step_s,
        )

        dk_left = _current_properties(math.nextafter(h_s, -math.inf), parameters)[1]
        dtheta_left = _current_properties(
            math.nextafter(h_s, -math.inf),
            parameters,
        )[3]
        k_before_hs, _, theta_before_hs, _ = _current_properties(
            h_s - step_s,
            parameters,
        )
        _assert_derivative_matches(dk_left, (k_at_hs - k_before_hs) / step_s)
        _assert_derivative_matches(
            dtheta_left,
            (theta_at_hs - theta_before_hs) / step_s,
        )


MESH_COORDINATES = (
    (0.7, 0.0),
    (2.1, 0.3),
    (1.6, 1.8),
    (0.2, 1.1),
)
MESH_TRIANGLES = ((0, 1, 2), (0, 2, 3))
MESH_ANISOTROPY = ((1.7, 0.8, 0.23), (0.9, 1.4, -0.12))


def _assemble_current_system(
    heads,
    theta_old,
    parameters_by_node,
    *,
    kat,
    sink,
    source,
    dt,
):
    node_count = len(heads)
    properties = [
        _current_properties(head, parameters)
        for head, parameters in zip(heads, parameters_by_node)
    ]
    residual = [0.0] * node_count
    jacobian = [[0.0] * node_count for _ in range(node_count)]

    for triangle, anisotropy in zip(MESH_TRIANGLES, MESH_ANISOTROPY):
        node_1, node_2, node_3 = triangle
        nodes = (node_1, node_2, node_3)
        x_1, y_1 = MESH_COORDINATES[node_1]
        x_2, y_2 = MESH_COORDINATES[node_2]
        x_3, y_3 = MESH_COORDINATES[node_3]
        b_local = (y_2 - y_3, y_3 - y_1, y_1 - y_2)
        c_local = (x_3 - x_2, x_1 - x_3, x_2 - x_1)
        area = (c_local[2] * b_local[1] - c_local[1] * b_local[2]) / 2.0
        x_multiplier = 1.0
        if kat == 1:
            x_multiplier = 2.0 * math.pi * (x_1 + x_2 + x_3) / 3.0
        mass = x_multiplier * area / 3.0
        conductivity = sum(properties[node][0] for node in nodes) / 3.0
        sink_sum = sum(sink[node] for node in nodes)
        con_xx, con_zz, con_xz = anisotropy
        stiffness = [[0.0] * 3 for _ in range(3)]
        for local_row in range(3):
            for local_column in range(3):
                stiffness[local_row][local_column] = x_multiplier / (4.0 * area) * (
                    con_xx * b_local[local_row] * b_local[local_column]
                    + con_xz
                    * (
                        b_local[local_row] * c_local[local_column]
                        + c_local[local_row] * b_local[local_column]
                    )
                    + con_zz * c_local[local_row] * c_local[local_column]
                )

        for local_row, global_row in enumerate(nodes):
            gravity = 0.0
            if kat >= 1:
                gravity = x_multiplier / 2.0 * (
                    con_xz * b_local[local_row] + con_zz * c_local[local_row]
                )
            pressure_gravity = gravity + sum(
                stiffness[local_row][local_column] * heads[global_column]
                for local_column, global_column in enumerate(nodes)
            )
            sink_term = (
                x_multiplier
                * area
                / 12.0
                * (sink_sum + sink[global_row])
            )
            residual[global_row] += (
                conductivity * pressure_gravity
                + mass
                / dt
                * (properties[global_row][2] - theta_old[global_row])
                + sink_term
            )
            for local_column, global_column in enumerate(nodes):
                jacobian_term = (
                    conductivity * stiffness[local_row][local_column]
                    + properties[global_column][1] / 3.0 * pressure_gravity
                )
                if local_column == local_row:
                    jacobian_term += mass / dt * properties[global_row][3]
                jacobian[global_row][global_column] += jacobian_term

    return (
        [value - forcing for value, forcing in zip(residual, source)],
        jacobian,
    )


def _gravity_vector(heads, parameters_by_node, kat):
    gravity_vector = [0.0] * len(heads)
    properties = [
        _current_properties(head, parameters)
        for head, parameters in zip(heads, parameters_by_node)
    ]
    for triangle, anisotropy in zip(MESH_TRIANGLES, MESH_ANISOTROPY):
        node_1, node_2, node_3 = triangle
        nodes = (node_1, node_2, node_3)
        x_1, y_1 = MESH_COORDINATES[node_1]
        x_2, y_2 = MESH_COORDINATES[node_2]
        x_3, y_3 = MESH_COORDINATES[node_3]
        b_local = (y_2 - y_3, y_3 - y_1, y_1 - y_2)
        c_local = (x_3 - x_2, x_1 - x_3, x_2 - x_1)
        x_multiplier = 1.0
        if kat == 1:
            x_multiplier = 2.0 * math.pi * (x_1 + x_2 + x_3) / 3.0
        conductivity = sum(properties[node][0] for node in nodes) / 3.0
        _, con_zz, con_xz = anisotropy
        for local_row, global_row in enumerate(nodes):
            gravity_vector[global_row] += conductivity * x_multiplier / 2.0 * (
                con_xz * b_local[local_row] + con_zz * c_local[local_row]
            )
    return gravity_vector


def _norm(values):
    return math.sqrt(sum(value * value for value in values))


def test_mode6_current_assembler_is_connected_only_to_consistent_newton():
    source = (
        REPO_ROOT / "Soil Source" / "Watmov.for"
    ).read_text(encoding="utf-8", errors="ignore")
    code = "\n".join(
        line for line in source.splitlines() if not line.lower().startswith("c")
    )
    compact = re.sub(r"[\s!&]+", "", code.lower())
    routine_name = "assemblemode6currentresidualjacobian"
    start = compact.index(f"subroutine{routine_name}")
    end = compact.index("subroutineinitializewatermassbalance", start)
    assembler = compact[start:end]

    assert compact.count(f"subroutine{routine_name}") == 1
    solver_start = compact.index("subroutinesolvemode6fixedactivesetnewton")
    solver_end = compact.index(
        "subroutineevaluatemode6newtonmassbalance",
        solver_start,
    )
    assert f"call{routine_name}" in compact[solver_start:solver_end]
    assert "callsetmatcurrentpoint" in assembler
    assert "htemp" not in assembler
    assert "if(kat.eq.1)xmultiplier=2.0d0*pivalue*" in assembler
    assert "if(kat.ge.1)gravityterm=xmultiplier/2.0d0*" in assembler
    assert "condk*(blocal(localrow)*clocal(localcolumn)+" in assembler
    assert "dcon(globalcolumn)/3.0d0*pressuregravity" in assembler
    assert "masselement/dt*dtheta(globalrow)" in assembler
    assert "residual(i)=residual(i)-dble(q(i))" in assembler


def test_two_triangle_anisotropic_jacobian_matches_true_residual_directions():
    heads = (-120.0, -73.0, -46.0, -31.0)
    parameters_by_node = (
        HUTD06_PARAMETERS[0],
        HUTD06_PARAMETERS[3],
        HUTD06_PARAMETERS[5],
        HUTD06_PARAMETERS[6],
    )
    theta_old = tuple(
        _current_properties(head, parameters)[2] - storage_change
        for head, parameters, storage_change in zip(
            heads,
            parameters_by_node,
            (0.0020, 0.0015, 0.0025, 0.0010),
        )
    )
    sink = (0.02, 0.03, 0.01, 0.04)
    source = (0.11, -0.02, 0.03, 0.05)
    rng = random.Random(20260801)

    for kat in (1, 2):
        _, jacobian = _assemble_current_system(
            heads,
            theta_old,
            parameters_by_node,
            kat=kat,
            sink=sink,
            source=source,
            dt=0.002,
        )
        for _ in range(12):
            direction = [rng.uniform(-1.0, 1.0) for _ in heads]
            direction_norm = _norm(direction)
            step = 1.0e-5 / direction_norm
            heads_plus = tuple(
                head + step * value for head, value in zip(heads, direction)
            )
            heads_minus = tuple(
                head - step * value for head, value in zip(heads, direction)
            )
            residual_plus, _ = _assemble_current_system(
                heads_plus,
                theta_old,
                parameters_by_node,
                kat=kat,
                sink=sink,
                source=source,
                dt=0.002,
            )
            residual_minus, _ = _assemble_current_system(
                heads_minus,
                theta_old,
                parameters_by_node,
                kat=kat,
                sink=sink,
                source=source,
                dt=0.002,
            )
            finite_difference = [
                (plus - minus) / (2.0 * step)
                for plus, minus in zip(residual_plus, residual_minus)
            ]
            jacobian_direction = [
                sum(row[column] * direction[column] for column in range(4))
                for row in jacobian
            ]
            error = _norm(
                [
                    finite - analytical
                    for finite, analytical in zip(
                        finite_difference,
                        jacobian_direction,
                    )
                ]
            )
            scale = max(
                _norm(finite_difference),
                _norm(jacobian_direction),
                1.0,
            )
            assert error / scale < 1.0e-5


def test_source_storage_sink_and_gravity_signs_match_residual_contract():
    heads = (-95.0, -67.0, -49.0, -28.0)
    parameters_by_node = (HUTD06_PARAMETERS[4],) * 4
    theta_current = tuple(
        _current_properties(head, parameters_by_node[index])[2]
        for index, head in enumerate(heads)
    )
    zero = (0.0, 0.0, 0.0, 0.0)
    source = (0.13, -0.02, 0.04, 0.07)
    sink = (0.01, 0.02, 0.03, 0.04)

    residual_zero, _ = _assemble_current_system(
        heads,
        theta_current,
        parameters_by_node,
        kat=2,
        sink=zero,
        source=zero,
        dt=0.003,
    )
    residual_source, _ = _assemble_current_system(
        heads,
        theta_current,
        parameters_by_node,
        kat=2,
        sink=zero,
        source=source,
        dt=0.003,
    )
    for actual, baseline, forcing in zip(residual_source, residual_zero, source):
        assert math.isclose(actual - baseline, -forcing, abs_tol=1.0e-12)

    residual_sink, _ = _assemble_current_system(
        heads,
        theta_current,
        parameters_by_node,
        kat=2,
        sink=sink,
        source=zero,
        dt=0.003,
    )
    assert all(
        with_sink - without_sink > 0.0
        for with_sink, without_sink in zip(residual_sink, residual_zero)
    )

    theta_old = tuple(value - 0.001 for value in theta_current)
    residual_storage, _ = _assemble_current_system(
        heads,
        theta_old,
        parameters_by_node,
        kat=2,
        sink=zero,
        source=zero,
        dt=0.003,
    )
    assert all(
        with_storage - without_storage > 0.0
        for with_storage, without_storage in zip(residual_storage, residual_zero)
    )

    residual_no_gravity, _ = _assemble_current_system(
        heads,
        theta_current,
        parameters_by_node,
        kat=0,
        sink=zero,
        source=zero,
        dt=0.003,
    )
    expected_gravity = _gravity_vector(heads, parameters_by_node, kat=2)
    for with_gravity, without_gravity, expected in zip(
        residual_zero,
        residual_no_gravity,
        expected_gravity,
    ):
        assert math.isclose(
            with_gravity - without_gravity,
            expected,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )


def test_stiffness_is_symmetric_but_conductivity_derivative_is_not():
    parameters_by_node = (HUTD06_PARAMETERS[2],) * 4
    _, h_s = _branch_points(parameters_by_node[0])
    saturated_heads = (h_s + 1.0, h_s + 1.2, h_s + 0.8, h_s + 1.4)
    saturated_theta = (parameters_by_node[0][1],) * 4
    _, saturated_jacobian = _assemble_current_system(
        saturated_heads,
        saturated_theta,
        parameters_by_node,
        kat=0,
        sink=(0.0,) * 4,
        source=(0.0,) * 4,
        dt=0.002,
    )
    for row in range(4):
        for column in range(4):
            assert math.isclose(
                saturated_jacobian[row][column],
                saturated_jacobian[column][row],
                rel_tol=1.0e-13,
                abs_tol=1.0e-13,
            )

    dry_heads = (-130.0, -81.0, -44.0, -23.0)
    dry_theta = tuple(
        _current_properties(head, parameters_by_node[index])[2]
        for index, head in enumerate(dry_heads)
    )
    _, dry_jacobian = _assemble_current_system(
        dry_heads,
        dry_theta,
        parameters_by_node,
        kat=0,
        sink=(0.0,) * 4,
        source=(0.0,) * 4,
        dt=0.002,
    )
    asymmetry = max(
        abs(dry_jacobian[row][column] - dry_jacobian[column][row])
        for row in range(4)
        for column in range(4)
    )
    assert asymmetry > 1.0e-8


def _solve_dense(matrix, right_hand_side):
    size = len(right_hand_side)
    augmented = [
        [*map(float, matrix[row]), float(right_hand_side[row])]
        for row in range(size)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        assert abs(augmented[pivot][column]) > 1.0e-14
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(column + 1, size):
            factor = augmented[row][column] / augmented[column][column]
            for entry in range(column, size + 1):
                augmented[row][entry] -= factor * augmented[column][entry]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        solution[row] = (
            augmented[row][size]
            - sum(
                augmented[row][column] * solution[column]
                for column in range(row + 1, size)
            )
        ) / augmented[row][row]
    return solution


def _right_preconditioned_gmres(
    matrix,
    right_hand_side,
    right_preconditioner,
    *,
    restart,
    max_iterations,
    tolerance,
):
    size = len(right_hand_side)
    solution = [0.0] * size
    iterations = 0

    def matrix_vector(vector):
        return [
            sum(coefficient * value for coefficient, value in zip(row, vector))
            for row in matrix
        ]

    while iterations < max_iterations:
        product = matrix_vector(solution)
        residual = [
            right_hand_side[index] - product[index] for index in range(size)
        ]
        if max((abs(value) for value in residual), default=0.0) <= tolerance:
            return solution, iterations
        beta = _norm(residual)
        basis = [[value / beta for value in residual]]
        preconditioned_basis = []
        hessenberg = [[0.0] * restart for _ in range(restart + 1)]
        cosine = [0.0] * restart
        sine = [0.0] * restart
        projected_rhs = [beta] + [0.0] * restart
        inner_iterations = min(restart, max_iterations - iterations)

        for column in range(inner_iterations):
            preconditioned = right_preconditioner(basis[column])
            preconditioned_basis.append(preconditioned)
            work = matrix_vector(preconditioned)
            incoming_norm = _norm(work)
            for row in range(column + 1):
                coefficient = sum(
                    basis[row][index] * work[index] for index in range(size)
                )
                hessenberg[row][column] = coefficient
                work = [
                    value - coefficient * basis[row][index]
                    for index, value in enumerate(work)
                ]
            for row in range(column + 1):
                coefficient = sum(
                    basis[row][index] * work[index] for index in range(size)
                )
                hessenberg[row][column] += coefficient
                work = [
                    value - coefficient * basis[row][index]
                    for index, value in enumerate(work)
                ]
            next_norm = _norm(work)
            hessenberg[column + 1][column] = next_norm
            happy_breakdown = next_norm <= 1.0e-14 * max(incoming_norm, 1.0e-300)
            if not happy_breakdown:
                basis.append([value / next_norm for value in work])

            for row in range(column):
                rotated = (
                    cosine[row] * hessenberg[row][column]
                    + sine[row] * hessenberg[row + 1][column]
                )
                hessenberg[row + 1][column] = (
                    -sine[row] * hessenberg[row][column]
                    + cosine[row] * hessenberg[row + 1][column]
                )
                hessenberg[row][column] = rotated
            rotation_norm = math.hypot(
                hessenberg[column][column],
                hessenberg[column + 1][column],
            )
            assert rotation_norm > 0.0
            cosine[column] = hessenberg[column][column] / rotation_norm
            sine[column] = hessenberg[column + 1][column] / rotation_norm
            hessenberg[column][column] = rotation_norm
            hessenberg[column + 1][column] = 0.0
            rotated = (
                cosine[column] * projected_rhs[column]
                + sine[column] * projected_rhs[column + 1]
            )
            projected_rhs[column + 1] = (
                -sine[column] * projected_rhs[column]
                + cosine[column] * projected_rhs[column + 1]
            )
            projected_rhs[column] = rotated
            iterations += 1
            used = column + 1
            if abs(projected_rhs[column + 1]) <= tolerance or happy_breakdown:
                break

        coefficients = [0.0] * used
        for row in range(used - 1, -1, -1):
            coefficients[row] = (
                projected_rhs[row]
                - sum(
                    hessenberg[row][column] * coefficients[column]
                    for column in range(row + 1, used)
                )
            ) / hessenberg[row][row]
        for column, coefficient in enumerate(coefficients):
            solution = [
                value + coefficient * preconditioned_basis[column][index]
                for index, value in enumerate(solution)
            ]

    product = matrix_vector(solution)
    residual = [
        right_hand_side[index] - product[index] for index in range(size)
    ]
    assert max((abs(value) for value in residual), default=0.0) <= tolerance
    return solution, iterations


def _solve_small_current_newton(
    initial_heads,
    theta_old,
    parameters_by_node,
    source,
    *,
    sink,
    dt,
):
    heads = list(initial_heads)
    free_nodes = (1, 2, 3)
    residual_history = []
    alpha_history = []
    for _ in range(30):
        residual, jacobian = _assemble_current_system(
            heads,
            theta_old,
            parameters_by_node,
            kat=2,
            sink=sink,
            source=source,
            dt=dt,
        )
        free_residual = [residual[node] for node in free_nodes]
        residual_sum = sum(abs(value) for value in free_residual)
        residual_history.append(residual_sum)
        if residual_sum <= 1.0e-10:
            break
        free_jacobian = [
            [jacobian[row][column] for column in free_nodes]
            for row in free_nodes
        ]
        free_delta = _solve_dense(
            free_jacobian,
            [-value for value in free_residual],
        )
        jacobian_delta = [
            sum(
                free_jacobian[row][column] * free_delta[column]
                for column in range(len(free_nodes))
            )
            for row in range(len(free_nodes))
        ]
        slope = sum(
            residual_value * product_value
            for residual_value, product_value in zip(
                free_residual,
                jacobian_delta,
            )
        )
        assert slope < 0.0
        norm_squared = sum(value * value for value in free_residual)
        alpha = 1.0
        for line_search_step in range(13):
            trial_heads = list(heads)
            for node, delta in zip(free_nodes, free_delta):
                trial_heads[node] += alpha * delta
            trial_residual, _ = _assemble_current_system(
                trial_heads,
                theta_old,
                parameters_by_node,
                kat=2,
                sink=sink,
                source=source,
                dt=dt,
            )
            trial_norm_squared = sum(
                trial_residual[node] ** 2 for node in free_nodes
            )
            if 0.5 * trial_norm_squared <= (
                0.5 * norm_squared + 1.0e-4 * alpha * slope
            ):
                heads = trial_heads
                alpha_history.append(alpha)
                break
            if line_search_step < 12:
                alpha *= 0.5
        else:
            raise AssertionError("Armijo failed at alpha=2^-12")
    return heads, residual_history, alpha_history


def test_mode6_fixed_active_set_newton_contract():
    water_source = (
        REPO_ROOT / "Soil Source" / "Watmov.for"
    ).read_text(encoding="utf-8", errors="ignore")
    ortho_source = (
        REPO_ROOT / "Soil Source" / "ORTHOFEM.FOR"
    ).read_text(encoding="utf-8", errors="ignore")
    code = "\n".join(
        line for line in water_source.splitlines() if not line.lower().startswith("c")
    )
    compact = re.sub(r"[\s!&]+", "", code.lower())
    water_mover = compact[: compact.index("subroutineassemblemode6")]
    solver_start = compact.index("subroutinesolvemode6fixedactivesetnewton")
    solver_end = compact.index("subroutineevaluatemode6newtonmassbalance", solver_start)
    solver = compact[solver_start:solver_end]
    mass_end = compact.index("subroutineinitializewatermassbalance", solver_end)
    mode6_mass = compact[solver_end:mass_end]

    newton_call = water_mover.index("callsolvemode6fixedactivesetnewton")
    assert newton_call < water_mover.index("callsetmat(", newton_call)
    assert "goto6189" in water_mover
    failure_path = water_mover[
        water_mover.index("if(mode6newtonsuccess.ne.1)then") :
        water_mover.index("goto6189")
    ]
    assert "mode6continuation=0.25d0" in failure_path
    assert (
        "mode6continuation=0.5d0*(mode6continuation+"
        "mode6continuationaccepted)"
        in failure_path
    )
    assert "hnew(i)=mode6boundaryhead(i)" in failure_path
    assert "hnew(i)=basehold(i)" in failure_path
    assert (
        "if(dt.le.dtmin*(1.0d0+1.0d-12).and."
        "mode6continuationretryavailable.eq.0)"
        "mode6newtondetaileddiagnostics=1"
        in water_mover
    )
    assert (
        "if(mode6newtondetaileddiagnostics.eq.1)then"
        "write(*,*)'mode6newtonfinalfailure:"
        in failure_path
    )
    assert "mode6newtonrecoverablefailure:" not in water_mover
    assert "mode6newtonrecovered:failures=" not in water_mover
    assert "mode6newtondtcut:code=" in failure_path
    assert "'old_dt=',dt,'new_dt=',dmax1(dt/3.0d0,dtmin)" in failure_path
    assert "'cumulative_cut=',mode6retrycount" in failure_path
    assert "callilu(jacobian" in solver
    assert "callsolvemode6ilugmres(jacobian,linearrhs,a1" in solver
    assert "parameter(restartlength=30)" in solver
    assert "doubleprecision,allocatable::krylovbasis(:,:)" in solver
    assert "allocate(krylovbasis(numnodes,restartlength+1))" in solver
    assert "krylovbasis(maxnodes" not in solver
    assert "calllusolv(numnodes,maxneighbors" in solver
    assert (
        "callmatm2(work,matrix,preconditionedbasis(1,j),numnodes"
        in solver
    )
    assert solver.count("dotvalue=dotvalue+krylovbasis(i,k)*work(i)") == 1
    assert "seconddot=seconddot+krylovbasis(i,k)*work(i)" in solver
    assert "restartcount=restartcount+1" in solver
    assert "callmatm2(work,matrix,solution,numnodes" in solver
    assert "maxito,gmressuccess,gmresiterations,gmresrestarts" in solver
    assert "linearrhs(i)=-(jdelta+physicalresidual(i))" in solver
    assert "calllusolv(numnp,mbandd" in solver
    assert "if(gmressuccess.ne.1.or.linearerror.gt.lineartolerance)then" in solver
    assert (
        "if(detaileddiagnostics.eq.1)then"
        "if(failurecode.eq.4)then"
        "dolinesearchstep=1,linesearchcount"
        in solver
    )
    assert "calldiagnosemode6newtonfailure" in solver
    assert "jacobian(iadd(i),i)=1.0d0" in solver
    assert "linearrhs(i)=0.0d0" in solver
    assert "delta(i)=0.0d0" in solver
    assert "1.0d-4*alpha*slope" in solver
    assert "dolinesearchstep=0,linesearchmaximum" in solver
    assert "halfalpha=0.5d0*alpha" in solver
    assert "alpha=nextalpha" in solver
    assert "callsetmat(" not in solver
    assert "mode5" not in solver
    assert "mode6relax" not in solver
    assert "mode6trust" not in solver
    assert "qact(n)=sngl(physicalresidual(n)+dble(q(n)))" in solver
    assert (
        "soilair(i)=sngl(dmax1(dble(thsat(material))-"
        "thetacurrent,1.0d-4))"
        in solver
    )
    assert "thetacurrent.lt.dble(tlowerlimit(material))" in solver
    assert "thavail(i)=0.0" in solver
    assert (
        "dmin1(thetacurrent,dble(tupperlimit(material)))-"
        "dble(tlowerlimit(material))"
        in solver
    )
    assert "actualflux=dble(qact(n))" in mode6_mass
    assert "amass" not in mode6_mass
    assert "bmass" not in mode6_mass
    compact_ortho = re.sub(r"[\s!&]+", "", ortho_source.lower())
    assert (
        "if(resmax.lt.ecnvrg)goto200"
        "if(xratio.lt.rcnvrg)goto200"
        "if(dxnorm.lt.acnvrg)goto200"
        in compact_ortho
    )
    assert "mode6orthostatus" not in compact_ortho


def _assert_gmres_solution(matrix, expected, *, tolerance):
    right_hand_side = [
        sum(coefficient * value for coefficient, value in zip(row, expected))
        for row in matrix
    ]
    diagonal = [matrix[index][index] for index in range(len(matrix))]
    solution, iterations = _right_preconditioned_gmres(
        matrix,
        right_hand_side,
        lambda vector: [
            value / diagonal[index] for index, value in enumerate(vector)
        ],
        restart=4,
        max_iterations=20,
        tolerance=tolerance,
    )
    residual = [
        sum(coefficient * value for coefficient, value in zip(row, solution))
        - forcing
        for row, forcing in zip(matrix, right_hand_side)
    ]
    assert max(abs(value) for value in residual) <= tolerance
    assert iterations <= 8


def test_right_preconditioned_gmres_solves_nonsymmetric_ill_conditioned_system():
    matrix = [
        [1.0e-5, 2.0, -0.5, 0.0],
        [0.0, 3.0e2, 4.0, 1.0],
        [1.5, 0.0, 2.0e-2, -3.0],
        [0.2, -0.4, 0.0, 5.0],
    ]
    _assert_gmres_solution(matrix, [1.25, -0.75, 2.0, 0.5], tolerance=1.0e-10)


def test_right_preconditioned_gmres_solves_near_singular_system():
    epsilon = 1.0e-7
    matrix = [
        [1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0 + epsilon, 1.0, 1.0],
        [1.0, 1.0, 1.0 + 2.0 * epsilon, 1.0],
        [1.0, 1.0, 1.0, 1.0 + 3.0 * epsilon],
    ]
    _assert_gmres_solution(matrix, [0.5, -1.0, 1.5, 2.0], tolerance=1.0e-10)


def test_right_preconditioned_gmres_zero_rhs_exits_without_iteration():
    matrix = [
        [2.0, -1.0, 0.0, 0.0],
        [0.5, 3.0, 1.0, 0.0],
        [0.0, -0.2, 4.0, 1.0],
        [1.0, 0.0, 0.5, 2.0],
    ]
    solution, iterations = _right_preconditioned_gmres(
        matrix,
        [0.0, 0.0, 0.0, 0.0],
        lambda vector: list(vector),
        restart=3,
        max_iterations=20,
        tolerance=1.0e-12,
    )
    assert solution == [0.0, 0.0, 0.0, 0.0]
    assert iterations == 0


def test_mode6_dedicated_gmres_preserves_legacy_orthomin_modes():
    def compact_fortran(path):
        source = path.read_text(encoding="utf-8", errors="ignore")
        code = "\n".join(
            line
            for line in source.splitlines()
            if not line.lower().startswith("c")
        )
        return re.sub(r"[\s!&]+", "", code.lower())

    public = compact_fortran(REPO_ROOT / "Soil Source" / "public.ins")
    water = compact_fortran(REPO_ROOT / "Soil Source" / "Watmov.for")
    root = compact_fortran(REPO_ROOT / "Soil Source" / "root_diff_new.for")
    heat = compact_fortran(REPO_ROOT / "Soil Source" / "HEATMOV.FOR")
    solute = compact_fortran(REPO_ROOT / "Soil Source" / "solmov.for")

    assert "nmatd=15,mnorth=4" in public
    assert "subroutinesolvemode6ilugmres" in water
    assert "waterecnvrg,waterrcnvrg,wateracnvrg,0,mnorth,maxito,1)" in water
    assert "ecnvrg,rcnvrg,acnvrg,4,mnorth,maxito,6)" in root
    assert "ecnvrg,rcnvrg,acnvrg,4,mnorth,maxito,3)" in heat
    assert "ecnvrg,rcnvrg,acnvrg,0,mnorth,maxito,2)" in solute


def test_small_consistent_newton_residual_is_monotone_and_convergent():
    parameters_by_node = (HUTD06_PARAMETERS[2],) * 4
    target_heads = (-75.0, -62.0, -49.0, -36.0)
    theta_old = tuple(
        _current_properties(head, parameters_by_node[index])[2] - increment
        for index, (head, increment) in enumerate(
            zip(target_heads, (0.0010, 0.0014, 0.0018, 0.0012))
        )
    )
    sink = (0.006, 0.008, 0.005, 0.007)
    zero_source = (0.0,) * 4
    residual_at_target, _ = _assemble_current_system(
        target_heads,
        theta_old,
        parameters_by_node,
        kat=2,
        sink=sink,
        source=zero_source,
        dt=0.01,
    )
    source = tuple(residual_at_target)
    solved_heads, residual_history, alpha_history = _solve_small_current_newton(
        (-75.0, -105.0, -78.0, -58.0),
        theta_old,
        parameters_by_node,
        source,
        sink=sink,
        dt=0.01,
    )

    assert len(residual_history) <= 16
    assert residual_history[-1] <= 1.0e-10
    assert all(
        next_value < value
        for value, next_value in zip(residual_history, residual_history[1:])
    )
    assert all(2.0**-12 <= alpha <= 1.0 for alpha in alpha_history)
    assert solved_heads[0] == -75.0
    for actual, expected in zip(solved_heads[1:], target_heads[1:]):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-7)


def test_newton_current_theta_updates_crop_facing_water_states():
    parameters = HUTD06_PARAMETERS[2]
    theta_s = parameters[1]
    theta_upper = _current_properties(-100.0, parameters)[2]
    theta_lower = _current_properties(-150000.0, parameters)[2]
    for head in (-150001.0, -500.0, -45.0, 0.0):
        theta_current = _current_properties(head, parameters)[2]
        soil_air = max(theta_s - theta_current, 1.0e-4)
        if theta_current < theta_lower:
            available = 0.0
        else:
            available = max(min(theta_current, theta_upper) - theta_lower, 0.0)

        assert soil_air >= 1.0e-4
        assert 0.0 <= available <= theta_upper - theta_lower
        if head >= 0.0:
            assert soil_air == 1.0e-4
            assert math.isclose(
                available,
                theta_upper - theta_lower,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
        if head < -150000.0:
            assert available == 0.0
