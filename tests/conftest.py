"""Load api.py and model.py without importing Home Assistant.

The package __init__ imports homeassistant; these modules do not, so they are
loaded under a stub package whose __path__ points at the component folder.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "salus_it500"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# Import the repo's custom_components package before the HA test harness puts
# its own testing_config/custom_components on sys.path; HA's loader then finds
# salus_it500.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
importlib.import_module("custom_components")

_pkg = types.ModuleType("salus_it500_core")
_pkg.__path__ = [str(COMPONENT_DIR)]
sys.modules.setdefault("salus_it500_core", _pkg)

api = importlib.import_module("salus_it500_core.api")
model = importlib.import_module("salus_it500_core.model")


def fixture_text(name: str) -> str:
    """Contents of a recorded API response."""
    return (FIXTURES / name).read_text(encoding="utf-8")
