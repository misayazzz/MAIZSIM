import copy
import json
import unittest

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401

from da_framework.faloye_2025_reference import (
    DEFAULT_DATA_PATH,
    DEFAULT_PROVENANCE_PATH,
    load_faloye_2025_soft_benchmark,
    validate_faloye_2025_soft_benchmark,
)


class Faloye2025ReferenceTests(unittest.TestCase):
    def test_default_artifacts_load_as_ten_row_soft_benchmark(self):
        benchmark = load_faloye_2025_soft_benchmark()

        self.assertEqual(len(benchmark.observations), 10)
        self.assertFalse(benchmark.can_determine_pass_fail)
        self.assertFalse(benchmark.can_determine_journal_ready)
        first = benchmark.observations[0]
        last = benchmark.observations[-1]
        self.assertEqual(first.benchmark_id, "faloye_2025_q1_t10")
        self.assertAlmostEqual(first.wetted_width_mean_cm, 6.50)
        self.assertAlmostEqual(first.wetted_depth_mean_cm, 9.00)
        self.assertEqual(last.benchmark_id, "faloye_2025_q2_t120")
        self.assertAlmostEqual(last.wetted_width_mean_cm, 26.80)
        self.assertAlmostEqual(last.wetted_depth_mean_cm, 29.00)

    def test_each_row_conserves_tabulated_emitter_volume(self):
        benchmark = load_faloye_2025_soft_benchmark()

        for observation in benchmark.observations:
            expected_volume = (
                observation.emitter_rate_l_h
                * observation.irrigation_time_min
                / 60.0
                * 1000.0
            )
            self.assertAlmostEqual(observation.applied_volume_cm3, expected_volume)

    def test_provenance_retains_unknown_spread_and_missing_hydraulics(self):
        benchmark = load_faloye_2025_soft_benchmark()
        provenance = benchmark.provenance

        self.assertEqual(
            provenance["statistical_reporting"]["reported_spread_semantics"],
            "unknown",
        )
        self.assertFalse(
            provenance["statistical_reporting"]["acceptance_threshold_allowed"]
        )
        missing = " ".join(
            provenance["missing_for_richards_solver_reproduction"]
        ).casefold()
        for required in ("theta_r", "theta_s", "van genuchten alpha", "ks", "hardpan"):
            self.assertIn(required, missing)
        self.assertEqual(provenance["license"]["identifier"], "CC BY 4.0")
        self.assertEqual(
            provenance["source_article"]["doi"],
            "10.3390/agronomy15020272",
        )
        self.assertEqual(
            provenance["journal_classification"]["broad_category_tier"],
            2,
        )

    def test_provenance_forbids_point_to_kat2_flow_mapping(self):
        geometry = load_faloye_2025_soft_benchmark().provenance["geometry"]
        mapping = geometry["flow_rate_mapping"]

        self.assertIn(
            "three-dimensional surface point source",
            geometry["faloye_reference_geometry"],
        )
        self.assertEqual(geometry["hutd06_geometry"]["kat"], 2)
        self.assertEqual(
            geometry["hutd06_geometry"]["coordinate_system"],
            "Cartesian vertical plane",
        )
        self.assertFalse(geometry["direct_geometry_compatibility"])
        self.assertFalse(mapping["direct_l_h_comparison_allowed"])
        self.assertFalse(
            mapping["model_representative_out_of_plane_length_cm_reported"]
        )
        self.assertFalse(mapping["may_assume_reported_spacing_as_representative_length"])
        self.assertEqual(mapping["paper_reports_intra_row_emitter_spacing_cm"], 30)

    def test_csv_hash_detects_numeric_tampering(self):
        csv_bytes = DEFAULT_DATA_PATH.read_bytes()
        provenance = _read_provenance()
        tampered = csv_bytes.replace(b",6.50,0.50,", b",6.51,0.50,", 1)

        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            validate_faloye_2025_soft_benchmark(tampered, provenance)

    def test_csv_hash_is_stable_across_git_line_endings(self):
        csv_bytes = DEFAULT_DATA_PATH.read_bytes()
        provenance = _read_provenance()
        crlf_bytes = csv_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

        benchmark = validate_faloye_2025_soft_benchmark(
            crlf_bytes,
            provenance,
        )

        self.assertEqual(len(benchmark.observations), 10)

    def test_validator_rejects_any_pass_fail_authority(self):
        provenance = copy.deepcopy(_read_provenance())
        provenance["decision_authority"]["can_determine_pass_fail"] = True

        with self.assertRaisesRegex(ValueError, "must be false"):
            validate_faloye_2025_soft_benchmark(
                DEFAULT_DATA_PATH.read_bytes(),
                provenance,
            )

    def test_validator_rejects_direct_kat2_lph_comparison(self):
        provenance = copy.deepcopy(_read_provenance())
        provenance["geometry"]["flow_rate_mapping"][
            "direct_l_h_comparison_allowed"
        ] = True

        with self.assertRaisesRegex(ValueError, "cannot be compared directly"):
            validate_faloye_2025_soft_benchmark(
                DEFAULT_DATA_PATH.read_bytes(),
                provenance,
            )


def _read_provenance():
    return json.loads(DEFAULT_PROVENANCE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
