"""Static checks for unsafe raw SQL patterns in application code (Phase 8)."""

from __future__ import annotations

import ast
from pathlib import Path


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2] / "app"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def test_no_fstring_or_percent_interpolation_in_sqlalchemy_text() -> None:
    """ORM code must not build SQL via f-strings or %-formatting inside ``text()``."""
    bad: list[str] = []

    for path in _iter_python_files(_app_root()):
        source = path.read_text(encoding="utf-8")
        if "text(" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "text":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.JoinedStr):
                bad.append(f"{path.relative_to(_app_root().parent)}:{node.lineno} text(f...)")
            if isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod):
                bad.append(f"{path.relative_to(_app_root().parent)}:{node.lineno} text%%...)")

    assert not bad, "Unsafe text() SQL interpolation:\n" + "\n".join(bad)
