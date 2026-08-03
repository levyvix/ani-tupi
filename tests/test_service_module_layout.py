"""Architectural guard for the ``services/`` layer (spec: service-module-layout).

Three rules, checked by walking the AST of every module under ``services/``:

1. Every service module declares its public API through ``__all__``.
2. No module imports a ``_``-prefixed symbol from another ``services/`` module.
   A helper needed outside its own module must be promoted to a public name.
3. No ``__init__.py`` under ``services/`` defines a function or a class at the
   top level. Package inits hold a docstring and re-exports, nothing else.

Without this guard all three rules are conventions that erode on the next feature.
"""

import ast
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent.parent / "services"


def _service_modules() -> list[Path]:
    return sorted(SERVICES_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_name(path: Path) -> str:
    relative = path.relative_to(SERVICES_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_from_import(node: ast.ImportFrom, module_name: str) -> str | None:
    """Return the absolute module a ``from ... import`` targets, if any."""
    if node.level == 0:
        return node.module
    package_parts = module_name.split(".")
    # A relative import inside a package resolves against the package itself.
    base = package_parts[: len(package_parts) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def _private_cross_module_imports(path: Path) -> list[str]:
    module_name = _module_name(path)
    violations: list[str] = []

    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.ImportFrom):
            continue
        target = _resolve_from_import(node, module_name)
        if not target or not target.startswith("services"):
            continue
        if target == module_name:
            continue
        for alias in node.names:
            if alias.name.startswith("_"):
                violations.append(f"{module_name} imports {alias.name!r} from {target}")

    return violations


def _declares_all(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Assign)
        and any(getattr(target, "id", "") == "__all__" for target in node.targets)
        for node in tree.body
    )


def test_every_service_module_declares_its_public_surface():
    violations = [
        str(path.relative_to(SERVICES_ROOT.parent))
        for path in _service_modules()
        if path.name != "__init__.py" and not _declares_all(_parse(path))
    ]

    assert not violations, (
        "Every module under services/ must declare its public API through "
        "__all__; symbols left out of it are internal to the module:\n  " + "\n  ".join(violations)
    )


def test_no_private_symbol_crosses_a_service_module_boundary():
    violations = [v for path in _service_modules() for v in _private_cross_module_imports(path)]

    assert not violations, (
        "Private (``_``-prefixed) symbols must not cross service module "
        "boundaries. Promote them to public names and add them to __all__:\n  "
        + "\n  ".join(violations)
    )


def test_service_package_inits_hold_no_logic():
    violations: list[str] = []

    for path in SERVICES_ROOT.rglob("__init__.py"):
        for node in _parse(path).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                violations.append(
                    f"{path.relative_to(SERVICES_ROOT.parent)} defines {node.name!r} "
                    f"at line {node.lineno}"
                )

    assert not violations, (
        "Package __init__.py files under services/ must contain only a "
        "docstring and re-exports:\n  " + "\n  ".join(violations)
    )
