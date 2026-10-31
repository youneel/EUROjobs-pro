"""YAML loading with a pure-Python fallback.

PyYAML is the preferred implementation. On very new Python versions where no
PyYAML wheel exists yet, ``ruamel.yaml`` (pure Python) is used instead so the
data files keep working without a C compiler.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - depends on the host environment
    import yaml as _pyyaml

    def safe_load(text: str) -> Any:
        return _pyyaml.safe_load(text)
except ModuleNotFoundError:  # pragma: no cover
    from ruamel.yaml import YAML

    _ruamel = YAML(typ="safe")

    def safe_load(text: str) -> Any:
        return _ruamel.load(text)


__all__ = ["safe_load"]
