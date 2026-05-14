import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    from . import context  # noqa: F401
except ImportError:  # pragma: no cover - supports direct file execution.
    import context  # noqa: F401
from da_framework.model_runner import run_model


class ModelRunnerTests(unittest.TestCase):
    def test_run_model_uses_absolute_paths_for_relative_run_dir(self):
        with tempfile.TemporaryDirectory(prefix="codex_model_runner_") as tmp_dir:
            root = Path(tmp_dir)
            member_dir = root / "members" / "000001"
            member_dir.mkdir(parents=True)
            (member_dir / "2dMAIZSIM.exe").write_text("", encoding="utf-8")
            (member_dir / "run.dat").write_text("", encoding="utf-8")

            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                expected_run_path = member_dir.resolve()
                with patch(
                    "da_framework.model_runner.subprocess.run",
                    return_value=SimpleNamespace(returncode=0),
                ) as subprocess_run:
                    result = run_model(Path("members") / "000001")
            finally:
                os.chdir(previous_cwd)

        subprocess_run.assert_called_once()
        command = subprocess_run.call_args.args[0]
        cwd = subprocess_run.call_args.kwargs["cwd"]
        self.assertEqual(
            command,
            [
                str(expected_run_path / "2dMAIZSIM.exe"),
                str(expected_run_path / "run.dat"),
            ],
        )
        self.assertEqual(cwd, expected_run_path)
        self.assertEqual(result.run_dir, expected_run_path)
        self.assertTrue(result.stdout_path.is_absolute())
        self.assertTrue(result.stderr_path.is_absolute())
        self.assertTrue(result.success)

    def test_run_model_missing_required_file_does_not_call_subprocess(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_model_runner_missing_",
        ) as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "run.dat").write_text("", encoding="utf-8")

            with patch("da_framework.model_runner.subprocess.run") as subprocess_run:
                result = run_model(run_dir)

        subprocess_run.assert_not_called()
        self.assertFalse(result.success)
        self.assertIn("Executable does not exist", result.message)
        self.assertTrue(result.run_dir.is_absolute())
        self.assertTrue(result.stderr_path.is_absolute())


if __name__ == "__main__":
    unittest.main()
