"""Test import helpers for the DA framework namespace package."""

from pathlib import Path
import sys


DA_FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DA_FRAMEWORK_ROOT.parent

if str(DA_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(DA_FRAMEWORK_ROOT))
