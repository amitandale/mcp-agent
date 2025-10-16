"""Compat layer exposing MCP protocol types while delegating to upstream modules."""

from importlib import metadata, util
import sys
from pathlib import Path

from . import types

__all__ = ["types"]

try:  # pragma: no cover - exercised only when upstream package is installed
    dist = metadata.distribution("mcp")
except metadata.PackageNotFoundError:  # pragma: no cover - CI/offline environments
    dist = None
else:
    package_dir = Path(dist.locate_file("mcp"))
    if package_dir.is_dir():
        upstream_path = str(package_dir)
        if upstream_path not in __path__:
            __path__.append(upstream_path)

        upstream_init = package_dir / "__init__.py"
        spec = util.spec_from_file_location(__name__, upstream_init)
        if spec is not None and spec.loader is not None:
            upstream_mod = util.module_from_spec(spec)
            original_module = sys.modules.get(__name__)
            sys.modules[spec.name] = upstream_mod
            sys.modules[__name__] = upstream_mod
            try:
                spec.loader.exec_module(upstream_mod)
            finally:
                sys.modules.pop(spec.name, None)
                if original_module is not None:
                    sys.modules[__name__] = original_module
                else:  # pragma: no cover - defensive cleanup
                    sys.modules.pop(__name__, None)
            exported = getattr(upstream_mod, "__all__", [])
            for name in exported:
                if name == "types" or name in globals():
                    continue
                globals()[name] = getattr(upstream_mod, name)
            __all__.extend(name for name in exported if name != "types")
