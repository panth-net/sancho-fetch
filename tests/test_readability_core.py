from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.shape

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "sancho"


def _all_py_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def test_no_nested_classes_or_inner_defs_in_src() -> None:
    offenders: list[str] = []

    for path in _all_py_files():
        tree = _parse(path)
        parent_by_node: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_by_node[child] = parent

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            parent = parent_by_node.get(node)

            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                offenders.append(
                    f"{path}: {type(node).__name__} '{getattr(node, 'name', '<anon>')}' nested inside function"
                )

            if isinstance(node, ast.ClassDef) and isinstance(parent, ast.ClassDef):
                offenders.append(f"{path}: class '{node.name}' nested inside class")

    assert not offenders, "\n".join(offenders)


def test_src_functions_have_type_hints_and_no_varargs() -> None:
    offenders: list[str] = []

    for path in _all_py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            if node.returns is None:
                offenders.append(f"{path}: function '{node.name}' missing return type")

            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg in {"self", "cls"}:
                    continue
                if arg.annotation is None:
                    offenders.append(
                        f"{path}: function '{node.name}' arg '{arg.arg}' missing type annotation"
                    )

            if node.args.vararg is not None:
                offenders.append(f"{path}: function '{node.name}' uses *args")
            if node.args.kwarg is not None:
                offenders.append(f"{path}: function '{node.name}' uses **kwargs")

    assert not offenders, "\n".join(offenders)
