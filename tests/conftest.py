"""Pytest configuration and environment initialization for V.O.I.D.E."""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import voide
    if hasattr(voide, "__path__") and REPO_ROOT not in voide.__path__:
        voide.__path__.insert(0, REPO_ROOT)
except ImportError:
    import types
    voide_pkg = types.ModuleType("voide")
    voide_pkg.__path__ = [REPO_ROOT]
    sys.modules["voide"] = voide_pkg
