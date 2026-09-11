"""Test bootstrap.

The integration's pure modules (`pairing_code`, `store`, `matching`,
`advertisement`) deliberately import nothing from Home Assistant, so they can be
tested without installing it. Importing them normally would still execute
`custom_components/matterbook/__init__.py`, which does import Home Assistant, so
a stand-in package object is registered first: `import matterbook.store` then
finds `store.py` through this package's search path and never runs the real
`__init__.py`, while relative imports inside the module keep working.
"""

from __future__ import annotations

from pathlib import Path
import sys
import types

_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "matterbook"

if "matterbook" not in sys.modules:
    _package = types.ModuleType("matterbook")
    _package.__path__ = [str(_PACKAGE_DIR)]  # type: ignore[attr-defined]
    sys.modules["matterbook"] = _package
