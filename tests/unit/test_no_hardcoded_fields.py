"""Guard for docs/coding-guidelines.md §1: requirement fields live only in config.

Any string literal in src/ (or a backtick/quoted word in prompts/) that equals a field name
from config/requirement.yaml means someone hard-coded a field. Put the behaviour in the
config instead (see "Adding or removing a requirement field").
"""

import ast
import re
from pathlib import Path

from lead_capture.domain.schema import get_schema
from lead_capture.settings import ROOT


def string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_field_names_hard_coded_in_src():
    fields = set(get_schema().field_names())
    offenders = [
        f"{path.relative_to(ROOT)}:{line}: {value!r}"
        for path in sorted((ROOT / "src").rglob("*.py"))
        for line, value in string_literals(path)
        if value in fields
    ]
    assert offenders == [], "field names hard-coded (use config/requirement.yaml):\n" + "\n".join(
        offenders
    )


def test_no_field_names_hard_coded_in_prompts():
    fields = set(get_schema().field_names())
    offenders = []
    for path in sorted((ROOT / "prompts").glob("*.md")):
        for word in re.findall(r"[`\"']([a-z_]+)[`\"']", path.read_text()):
            if word in fields:
                offenders.append(f"{path.name}: {word}")
    assert offenders == []
