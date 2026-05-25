import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.hydrus_official_export import (
    HydrusDimensions,
    hydrus_shape_metrics,
    main,
    nearest_time_index,
    read_hydrus_dimensions_text,
    read_hydrus_mesh_bytes,
    read_hydrus_theta_output_bytes,
    read_official_project,
    theta_frame_dataframe,
)


class HydrusOfficialExportTests(unittest.TestCase):
    def test_read_hydrus_dimensions_text(self):
        dimensions = read_hydrus_dimensions_text(
            "\n".join(
                [
                    "Pcp_File_Version=3",
                    "  NumNPD  NumElD  NumBPD  MBandD  NSeepD  NumSPD    NDrD  NElDrD   NMatD   NObsD     NSD   NAnis",
                    "       4       2       3      30       1       1       1      20       1       3       1",
                ]
            )
        )

        self.assertEqual(dimensions.node_count, 4)
        self.assertEqual(dimensions.element_count, 2)
        self.assertEqual(dimensions.boundary_node_count, 3)
        self.assertEqual(dimensions.material_count, 1)
        self.assertEqual(dimensions.observation_node_count, 3)

    def test_read_hydrus_mesh_bytes_converts_y_to_depth_and_areas(self):
        dimensions = HydrusDimensions(
            node_count=4,
            element_count=2,
            boundary_node_count=0,
            material_count=1,
            observation_node_count=0,
        )
        mesh = read_hydrus_mesh_bytes(_mesh_bytes(), dimensions)

        np.testing.assert_allclose(mesh.nodes["x_cm"], [0.0, 0.0, 10.0, 10.0])
        np.testing.assert_allclose(mesh.nodes["z_cm"], [10.0, 0.0, 0.0, 10.0])
        np.testing.assert_allclose(mesh.nodes["depth_cm"], [0.0, 10.0, 10.0, 0.0])
        self.assertEqual(len(mesh.elements), 2)
        self.assertAlmostEqual(float(mesh.nodes["area_cm2"].sum()), 100.0)
        self.assertTrue((mesh.nodes["area_cm2"] > 0.0).all())

    def test_read_hydrus_theta_output_bytes_uses_time_plus_node_values(self):
        theta = read_hydrus_theta_output_bytes(_theta_bytes(), node_count=4)

        np.testing.assert_allclose(theta.times_h, [0.0, 2.0])
        np.testing.assert_allclose(
            theta.theta,
            [
                [0.20, 0.20, 0.20, 0.20],
                [0.40, 0.30, 0.24, 0.22],
            ],
        )
        self.assertEqual(nearest_time_index(theta.times_h, 1.7), 1)

    def test_theta_frame_and_shape_metrics(self):
        dimensions = HydrusDimensions(4, 2, 0, 1, 0)
        mesh = read_hydrus_mesh_bytes(_mesh_bytes(), dimensions)
        theta = read_hydrus_theta_output_bytes(_theta_bytes(), node_count=4)

        frame = theta_frame_dataframe(mesh, theta, 2.0)
        metrics = hydrus_shape_metrics(
            mesh,
            theta,
            output_time_h=2.0,
            baseline_time_h=0.0,
            wet_delta_threshold=0.05,
        )

        self.assertEqual(
            list(frame.columns),
            ["node", "time_h", "x_cm", "z_cm", "depth_cm", "theta", "area_cm2"],
        )
        self.assertAlmostEqual(float(frame.loc[0, "theta"]), 0.40)
        self.assertEqual(metrics["wet_node_count"], 2)
        self.assertAlmostEqual(metrics["cross_section_area_cm2"], 100.0)
        self.assertAlmostEqual(metrics["peak_delta_x_cm"], 0.0)
        self.assertAlmostEqual(metrics["peak_delta_depth_cm"], 0.0)

    def test_cli_writes_csv_summary_manifest_and_figure_from_extracted_dir(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_official_") as tmp_dir:
            root = Path(tmp_dir)
            project_dir = root / "DripMini"
            output_dir = root / "out"
            project_dir.mkdir()
            _write_project_dir(project_dir)

            exit_code = main(
                [
                    "--project-dir",
                    str(project_dir),
                    "--output-dir",
                    str(output_dir),
                    "--prefix",
                    "mini",
                    "--output-time-h",
                    "2",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "mini_theta_baseline.csv").exists())
            self.assertTrue((output_dir / "mini_theta_output.csv").exists())
            self.assertTrue((output_dir / "mini_mesh_nodes.csv").exists())
            self.assertTrue((output_dir / "mini_mesh_elements.csv").exists())
            self.assertTrue((output_dir / "mini_summary.csv").exists())
            self.assertTrue((output_dir / "mini_hydrus_fields.png").exists())
            self.assertTrue((output_dir / "mini_hydrus_manifest.json").exists())
            summary = pd.read_csv(output_dir / "mini_summary.csv")
            self.assertAlmostEqual(float(summary.loc[0, "output_time_h"]), 2.0)

    def test_read_official_project_from_extracted_dir(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_project_") as tmp_dir:
            project_dir = Path(tmp_dir)
            _write_project_dir(project_dir)

            project = read_official_project(project_dir=project_dir)

        self.assertEqual(project.dimensions.node_count, 4)
        self.assertEqual(project.mesh.elements.shape[0], 2)
        np.testing.assert_allclose(project.theta_output.times_h, [0.0, 2.0])
        self.assertEqual(project.selector_metadata["kat"], 1)


def _write_project_dir(path):
    (path / "Hydrus3D Files 1.00__DIMENSIO.IN").write_text(
        "\n".join(
            [
                "Pcp_File_Version=3",
                "  NumNPD  NumElD  NumBPD  MBandD  NSeepD  NumSPD    NDrD  NElDrD   NMatD   NObsD     NSD   NAnis",
                "       4       2       3      30       1       1       1      20       1       3       1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "Hydrus3D Files 1.00__SELECTOR.IN").write_text(
        "\n".join(
            [
                "LUnit  TUnit  MUnit",
                "cm",
                "hours",
                "mmol",
                "Kat (0:horizontal plane, 1:axisymmetric vertical flow, 2:vertical plane)",
                "  1",
                "  thr    ths   Alfa     n         Ks      l",
                " 0.078   0.43  0.036   1.56       1.04    0.5",
                "      tInit        tMax",
                "          0           2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "Hydrus3D Files 1.00__MESHTRIA.000").write_bytes(_mesh_bytes())
    (path / "Hydrus3D Files 1.00__th.out").write_bytes(_theta_bytes())


def _mesh_bytes():
    header = b"Pcp_File_Version=" + struct.pack("<Hiiii", 1, 4, 0, 2, 0)
    nodes = b"".join(
        struct.pack("<ffff", *node)
        for node in (
            (0.0, 10.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0, 0.0),
            (10.0, 10.0, 0.0, 0.0),
        )
    )
    elements = struct.pack("<iiiiii", 1, 2, 3, 1, 3, 4)
    return header + nodes + elements


def _theta_bytes():
    return struct.pack(
        "<ffffffffff",
        0.0,
        0.20,
        0.20,
        0.20,
        0.20,
        2.0,
        0.40,
        0.30,
        0.24,
        0.22,
    )


if __name__ == "__main__":
    unittest.main()
