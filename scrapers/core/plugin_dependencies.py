"""Helpers for plugins that depend on optional runtime packages."""

from importlib.util import find_spec
from types import ModuleType

from utils.logging import get_logger

logger = get_logger(__name__)


def optional_dependencies_available(plugin_module: ModuleType, plugin_name: str) -> bool:
    """Check declared optional dependencies and explain how to install missing ones.

    Plugins declare ``OPTIONAL_DEPENDENCIES`` as a mapping of importable module
    names to the package extra that provides them, for example
    ``{"selenium": "browser-scrapers"}``.
    """
    dependencies = getattr(plugin_module, "OPTIONAL_DEPENDENCIES", {})
    missing = [
        (module_name, extra)
        for module_name, extra in dependencies.items()
        if not _module_is_available(module_name)
    ]
    if not missing:
        return True

    details = ", ".join(f"{module_name} (extra: {extra})" for module_name, extra in missing)
    extras = sorted({extra for _, extra in missing})
    install_target = f"ani-tupi[{','.join(extras)}]"
    logger.warning(
        f"Skipping scraper plugin {plugin_name}: missing optional dependency {details}. "
        f"Install it with: uv tool install '{install_target}' "
        f"(or pip install '{install_target}')"
    )
    return False


def _module_is_available(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False
