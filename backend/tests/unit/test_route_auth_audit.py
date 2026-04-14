"""Route auth audit tests.

These tests intentionally inspect source code structure instead of importing the
fully booted app. The current local bootstrap still has import-time DB/env
coupling, but the issue #10 rule is structural: public exceptions are explicit
and every other endpoint declares get_current_user.
"""

import ast
from pathlib import Path

_ENDPOINT_DIR = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints"
_PUBLIC_ENDPOINTS = {
    ("health.py", "health_check"),
    ("auth.py", "register"),
    ("auth.py", "login"),
    ("auth.py", "refresh"),
}


def _route_functions(module_path: Path) -> list[ast.AsyncFunctionDef]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    return [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)]


def _is_route_function(node: ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if decorator.func.attr in {"get", "post", "patch", "delete", "put"}:
                return True
    return False


def _uses_get_current_user(node: ast.AsyncFunctionDef) -> bool:
    for default in node.args.defaults:
        if not isinstance(default, ast.Call):
            continue
        if not isinstance(default.func, ast.Name) or default.func.id != "Depends":
            continue
        if not default.args:
            continue
        dep = default.args[0]
        if isinstance(dep, ast.Name) and dep.id == "get_current_user":
            return True
    return False


def test_non_public_endpoints_require_get_current_user() -> None:
    protected_routes: list[tuple[str, str]] = []

    for module_path in sorted(_ENDPOINT_DIR.glob("*.py")):
        for node in _route_functions(module_path):
            route_id = (module_path.name, node.name)
            if not _is_route_function(node) or route_id in _PUBLIC_ENDPOINTS:
                continue
            protected_routes.append(route_id)

    assert protected_routes
    for route_id in protected_routes:
        module_path = _ENDPOINT_DIR / route_id[0]
        route = next(node for node in _route_functions(module_path) if node.name == route_id[1])
        assert _uses_get_current_user(route), (
            f"{route_id[0]}:{route_id[1]} must depend on get_current_user"
        )


def test_main_disables_docs_routes_in_production() -> None:
    main_path = Path(__file__).resolve().parents[2] / "app" / "main.py"
    source = main_path.read_text(encoding="utf-8")

    assert 'docs_url = None if app_settings.is_production else "/docs"' in source
    assert 'redoc_url = None if app_settings.is_production else "/redoc"' in source
    assert 'openapi_url = None if app_settings.is_production else "/openapi.json"' in source
