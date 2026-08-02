"""Load and audit the Faloye et al. (2025) soft wetting-front benchmark."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path


REFERENCE_DIRECTORY = Path(__file__).resolve().parents[1] / "reference"
DEFAULT_DATA_PATH = REFERENCE_DIRECTORY / "faloye_2025_wetting_front.csv"
DEFAULT_PROVENANCE_PATH = (
    REFERENCE_DIRECTORY / "faloye_2025_wetting_front_provenance.json"
)
EXPECTED_DATA_SHA256 = "8968AFF5CB88BD4E4617F27033F142E511A1DAEA84CDBD65C66EC9E9D64A5515"
EXPECTED_SOURCE_PDF_SHA256 = (
    "BCEE7B215D4A77F3F49719F5B8EC693EC689E49D7F0D7C331F700A4C48802D60"
)

EXPECTED_COLUMNS = (
    "benchmark_id",
    "treatment",
    "emitter_head_cm",
    "emitter_rate_l_h",
    "irrigation_time_min",
    "applied_volume_cm3",
    "wetted_width_mean_cm",
    "wetted_width_reported_spread_cm",
    "wetted_depth_mean_cm",
    "wetted_depth_reported_spread_cm",
    "replicate_count",
    "source_table",
)
EXPECTED_TREATMENT_TIMES = {
    "Q1": (10.0, 20.0, 30.0, 60.0, 120.0),
    "Q2": (10.0, 20.0, 30.0, 60.0, 120.0),
}
EXPECTED_TREATMENT_CONDITIONS = {
    "Q1": (10.0, 0.12),
    "Q2": (20.0, 0.18),
}


@dataclass(frozen=True)
class FaloyeObservation:
    """One aggregate wetting-front observation transcribed from Table 2."""

    benchmark_id: str
    treatment: str
    emitter_head_cm: float
    emitter_rate_l_h: float
    irrigation_time_min: float
    applied_volume_cm3: float
    wetted_width_mean_cm: float
    wetted_width_reported_spread_cm: float
    wetted_depth_mean_cm: float
    wetted_depth_reported_spread_cm: float
    replicate_count: int
    source_table: str


@dataclass(frozen=True)
class FaloyeSoftBenchmark:
    """Audited data and provenance with explicitly diagnostic-only authority."""

    observations: tuple[FaloyeObservation, ...]
    provenance: dict

    @property
    def can_determine_pass_fail(self):
        return False

    @property
    def can_determine_journal_ready(self):
        return False


def load_faloye_2025_soft_benchmark(
    data_path=DEFAULT_DATA_PATH,
    provenance_path=DEFAULT_PROVENANCE_PATH,
):
    """Load and validate the immutable soft-benchmark artifacts."""
    data_path = Path(data_path)
    provenance_path = Path(provenance_path)
    csv_bytes = data_path.read_bytes()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    artifact = _mapping(provenance, "data_artifact")
    if artifact.get("path") != data_path.name:
        raise ValueError(
            "Faloye provenance data_artifact.path does not match the CSV filename."
        )
    return validate_faloye_2025_soft_benchmark(csv_bytes, provenance)


def validate_faloye_2025_soft_benchmark(csv_bytes, provenance):
    """Validate source integrity, numerical invariants, and soft-only policy."""
    if not isinstance(csv_bytes, bytes):
        raise TypeError("Faloye CSV content must be provided as bytes.")
    if not isinstance(provenance, dict):
        raise TypeError("Faloye provenance must be a JSON object.")

    _validate_provenance_policy(provenance)
    _validate_csv_hash(csv_bytes, provenance)
    observations = _parse_observations(csv_bytes)
    _validate_observation_matrix(observations, provenance)
    return FaloyeSoftBenchmark(
        observations=tuple(observations),
        provenance=provenance,
    )


def _validate_provenance_policy(provenance):
    if provenance.get("benchmark_class") != "soft_external_behavioral_benchmark":
        raise ValueError("Faloye benchmark_class must remain soft-only.")
    if provenance.get("role") != "diagnostic_only":
        raise ValueError("Faloye benchmark role must remain diagnostic_only.")

    authority = _mapping(provenance, "decision_authority")
    for field in (
        "can_determine_pass_fail",
        "can_determine_journal_ready",
        "can_satisfy_external_field_validation_gate",
    ):
        if authority.get(field) is not False:
            raise ValueError(f"Faloye decision_authority.{field} must be false.")

    statistics = _mapping(provenance, "statistical_reporting")
    if statistics.get("reported_spread_semantics") != "unknown":
        raise ValueError("Faloye reported spread must remain explicitly unknown.")
    if statistics.get("acceptance_threshold_allowed") is not False:
        raise ValueError("Faloye spread cannot be used as an acceptance threshold.")

    geometry = _mapping(provenance, "geometry")
    if geometry.get("direct_geometry_compatibility") is not False:
        raise ValueError("Faloye point-source geometry is not directly KAT=2-compatible.")
    if (
        geometry.get("wetted_width_semantics")
        != "likely_full_cross_section_width_but_not_explicitly_confirmed"
    ):
        raise ValueError("Faloye wetted width must remain explicitly uncertain.")
    faloye_geometry = str(geometry.get("faloye_reference_geometry", "")).casefold()
    if "three-dimensional surface point source" not in faloye_geometry:
        raise ValueError("Faloye provenance must retain its 3D point-source geometry.")
    if "axisymmetric" not in faloye_geometry:
        raise ValueError("Faloye provenance must retain the axisymmetric approximation.")
    hutd06 = _mapping(geometry, "hutd06_geometry")
    if hutd06.get("kat") != 2:
        raise ValueError("Faloye geometry audit must identify HUTD06 KAT=2.")
    if hutd06.get("coordinate_system") != "Cartesian vertical plane":
        raise ValueError("Faloye geometry audit must retain the KAT=2 plane geometry.")
    flow_mapping = _mapping(geometry, "flow_rate_mapping")
    if flow_mapping.get("direct_l_h_comparison_allowed") is not False:
        raise ValueError("Faloye L/h cannot be compared directly with a KAT=2 line source.")
    if (
        flow_mapping.get("model_representative_out_of_plane_length_cm_reported")
        is not False
    ):
        raise ValueError(
            "Faloye provenance must not invent an HUTD06 out-of-plane length."
        )
    if flow_mapping.get("may_assume_reported_spacing_as_representative_length") is not False:
        raise ValueError(
            "Faloye emitter spacing cannot be assumed as the model line length."
        )

    source = _mapping(provenance, "source_article")
    if source.get("doi") != "10.3390/agronomy15020272":
        raise ValueError("Faloye DOI does not match the audited article.")
    source_pdf = _mapping(provenance, "source_pdf")
    if source_pdf.get("sha256") != EXPECTED_SOURCE_PDF_SHA256:
        raise ValueError("Faloye source PDF SHA-256 does not match the audited PDF.")
    license_metadata = _mapping(provenance, "license")
    if license_metadata.get("identifier") != "CC BY 4.0":
        raise ValueError("Faloye aggregate transcription must retain CC BY 4.0.")
    classification = _mapping(provenance, "journal_classification")
    if classification.get("version") != "March 2025 upgraded edition":
        raise ValueError("Faloye provenance must retain the 2025 CAS partition version.")
    if classification.get("broad_category_tier") != 2:
        raise ValueError("Faloye provenance must retain the public CAS tier-2 evidence.")

    missing = provenance.get("missing_for_richards_solver_reproduction")
    if not isinstance(missing, list):
        raise ValueError("Faloye provenance requires a Richards-parameter gap list.")
    missing_text = " ".join(str(item) for item in missing).casefold()
    for required in ("theta_r", "theta_s", "van genuchten alpha", "ks", "hardpan"):
        if required not in missing_text:
            raise ValueError(f"Faloye provenance must retain the missing {required} gap.")


def _validate_csv_hash(csv_bytes, provenance):
    artifact = _mapping(provenance, "data_artifact")
    expected_hash = artifact.get("sha256")
    if expected_hash != EXPECTED_DATA_SHA256:
        raise ValueError("Faloye provenance CSV SHA-256 is not the audited data hash.")
    if (
        artifact.get("hash_scope")
        != "UTF-8 CSV bytes after CRLF and CR line endings are normalized to LF."
    ):
        raise ValueError("Faloye provenance must retain the canonical CSV hash scope.")
    canonical_bytes = csv_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    actual_hash = hashlib.sha256(canonical_bytes).hexdigest()
    if actual_hash.casefold() != str(expected_hash).casefold():
        raise ValueError(
            "Faloye CSV SHA-256 mismatch: "
            f"expected {expected_hash}, got {actual_hash.upper()}."
        )


def _parse_observations(csv_bytes):
    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Faloye CSV must be UTF-8 encoded.") from error

    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise ValueError(
            "Faloye CSV columns do not match the audited schema: "
            f"{reader.fieldnames!r}."
        )

    observations = []
    for line_number, row in enumerate(reader, start=2):
        try:
            observation = FaloyeObservation(
                benchmark_id=_required_text(row, "benchmark_id"),
                treatment=_required_text(row, "treatment"),
                emitter_head_cm=_positive_float(row, "emitter_head_cm"),
                emitter_rate_l_h=_positive_float(row, "emitter_rate_l_h"),
                irrigation_time_min=_positive_float(row, "irrigation_time_min"),
                applied_volume_cm3=_positive_float(row, "applied_volume_cm3"),
                wetted_width_mean_cm=_positive_float(row, "wetted_width_mean_cm"),
                wetted_width_reported_spread_cm=_positive_float(
                    row,
                    "wetted_width_reported_spread_cm",
                ),
                wetted_depth_mean_cm=_positive_float(row, "wetted_depth_mean_cm"),
                wetted_depth_reported_spread_cm=_positive_float(
                    row,
                    "wetted_depth_reported_spread_cm",
                ),
                replicate_count=_positive_int(row, "replicate_count"),
                source_table=_required_text(row, "source_table"),
            )
        except ValueError as error:
            raise ValueError(f"Invalid Faloye CSV row {line_number}: {error}") from error
        observations.append(observation)
    return observations


def _validate_observation_matrix(observations, provenance):
    artifact = _mapping(provenance, "data_artifact")
    expected_count = artifact.get("row_count")
    if len(observations) != expected_count or expected_count != 10:
        raise ValueError(
            f"Faloye benchmark requires exactly 10 rows, got {len(observations)}."
        )

    seen_ids = set()
    observed_times = {treatment: [] for treatment in EXPECTED_TREATMENT_TIMES}
    for observation in observations:
        if observation.benchmark_id in seen_ids:
            raise ValueError(f"Duplicate Faloye benchmark id: {observation.benchmark_id}.")
        seen_ids.add(observation.benchmark_id)
        if observation.treatment not in EXPECTED_TREATMENT_CONDITIONS:
            raise ValueError(f"Unknown Faloye treatment: {observation.treatment}.")

        expected_head, expected_rate = EXPECTED_TREATMENT_CONDITIONS[
            observation.treatment
        ]
        if not math.isclose(observation.emitter_head_cm, expected_head):
            raise ValueError(
                f"{observation.treatment} emitter head must be {expected_head} cm."
            )
        if not math.isclose(observation.emitter_rate_l_h, expected_rate):
            raise ValueError(
                f"{observation.treatment} emitter rate must be {expected_rate} L/h."
            )
        expected_volume = (
            observation.emitter_rate_l_h
            * observation.irrigation_time_min
            / 60.0
            * 1000.0
        )
        if not math.isclose(
            observation.applied_volume_cm3,
            expected_volume,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"{observation.benchmark_id} applied volume violates q*t conservation."
            )
        if observation.replicate_count != 3:
            raise ValueError("Faloye aggregate rows must retain three replicates.")
        if observation.source_table != "Table 2":
            raise ValueError("Faloye aggregate rows must retain Table 2 provenance.")
        observed_times[observation.treatment].append(observation.irrigation_time_min)

    for treatment, expected_times in EXPECTED_TREATMENT_TIMES.items():
        if tuple(sorted(observed_times[treatment])) != expected_times:
            raise ValueError(
                f"{treatment} irrigation times do not match the audited Table 2 subset."
            )


def _mapping(parent, field):
    value = parent.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Faloye provenance field {field} must be an object.")
    return value


def _required_text(row, field):
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} is required.")
    return value


def _positive_float(row, field):
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric.") from error
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{field} must be finite and positive.")
    return value


def _positive_int(row, field):
    value = _positive_float(row, field)
    if not value.is_integer():
        raise ValueError(f"{field} must be an integer.")
    return int(value)
