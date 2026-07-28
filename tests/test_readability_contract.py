from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.shape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_MODULE_ROOT = ROOT / "src" / "sancho" / "templates" / "modules"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def _py_files() -> list[Path]:
    return sorted(TEMPLATE_MODULE_ROOT.rglob("*.py"))


def test_template_modules_have_no_classes_or_nested_defs() -> None:
    offenders: list[str] = []

    for path in _py_files():
        tree = _parse(path)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                offenders.append(f"{path}: class '{node.name}' not allowed in module templates")

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.stack: list[ast.AST] = []

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if self.stack:
                    offenders.append(f"{path}: nested function '{node.name}' at line {node.lineno}")
                self.stack.append(node)
                self.generic_visit(node)
                self.stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                if self.stack:
                    offenders.append(f"{path}: nested class '{node.name}' at line {node.lineno}")
                self.stack.append(node)
                self.generic_visit(node)
                self.stack.pop()

        Visitor().visit(tree)

    assert not offenders, "\n".join(offenders)


def test_template_functions_require_type_hints_and_no_varargs() -> None:
    offenders: list[str] = []

    for path in _py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            if node.returns is None:
                offenders.append(f"{path}: function '{node.name}' missing return type")

            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg == "self":
                    continue
                if arg.annotation is None:
                    offenders.append(f"{path}: function '{node.name}' arg '{arg.arg}' missing type")

            if node.args.vararg is not None:
                offenders.append(f"{path}: function '{node.name}' uses *args")
            if node.args.kwarg is not None:
                offenders.append(f"{path}: function '{node.name}' uses **kwargs")

    assert not offenders, "\n".join(offenders)


def test_main_run_signature_is_stable() -> None:
    offenders: list[str] = []

    for path in sorted(TEMPLATE_MODULE_ROOT.glob("*/main.py")):
        tree = _parse(path)
        run_fns = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"]
        if len(run_fns) != 1:
            offenders.append(f"{path}: expected exactly one top-level run() function")
            continue

        run_fn = run_fns[0]
        kwonly = [arg.arg for arg in run_fn.args.kwonlyargs]
        if kwonly != ["context", "payload"]:
            offenders.append(
                f"{path}: run() kwargs must be exactly ['context', 'payload'], got {kwonly}"
            )

    assert not offenders, "\n".join(offenders)
