"""Check the Python examples in the Cyberwave docs against the installed SDK.

For every ```python block on the pages in PAGES, this finds:

- calls on a client created with ``Cyberwave(...)``, like ``cw.twin(...)``
- calls on a twin returned by ``cw.twin(...)`` or ``cw.twins(...)``, like
  ``arm.joints.set(...)``

and checks that each attribute exists in the SDK and, for client calls, that
it can be called. Twin calls are checked against every Twin class the SDK
exports, because which class a catalog asset resolves to is only known at
runtime. That makes the twin check lenient: it can miss a method that exists
on the wrong class, but it never reports a method that exists somewhere.

Exit code is 1 if any call is broken, so this can run in CI.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import urllib.request
from dataclasses import dataclass
from importlib.metadata import version

DOCS = "https://docs.cyberwave.com"
PAGES = [
    "overview/index",
    "overview/hello-robot",
    "overview/tools/python-sdk",
    "overview/features/teleoperation-and-remote-control",
    "overview/features/models-and-datasets",
]

FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
SELF_ASSIGN = re.compile(r"self\.([A-Za-z_]\w*)\s*[:=]")


@dataclass(frozen=True)
class Call:
    page: str
    line: int
    code: str
    kind: str  # "client" or "twin"
    attr: str


@dataclass(frozen=True)
class Result:
    call: Call
    ok: bool
    reason: str


def fetch(page: str) -> str:
    with urllib.request.urlopen(f"{DOCS}/{page}.md", timeout=30) as resp:
        return resp.read().decode("utf-8")


def python_blocks(markdown: str) -> list[tuple[int, str]]:
    """Return (first line number in the page, code) for each python fence."""
    blocks = []
    for match in FENCE.finditer(markdown):
        start_line = markdown.count("\n", 0, match.start(1)) + 1
        blocks.append((start_line, match.group(1)))
    return blocks


def _root_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def find_calls(
    page: str,
    start_line: int,
    code: str,
    clients: set[str],
    twins: set[str],
) -> list[Call]:
    """Find client and twin attribute calls in one code block.

    ``clients`` and ``twins`` hold variable names seen in earlier blocks on the
    same page, because docs often define ``cw`` once and reuse it. Both sets
    are updated in place.
    """
    tree = ast.parse(code)
    lines = code.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        func = node.value.func
        if isinstance(func, ast.Name) and func.id == "Cyberwave":
            clients.update(targets)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in {"twin", "twins"}
            and _root_name(func.value) in clients
        ):
            twins.update(targets)

    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        root = _root_name(node.value)
        if root in clients:
            kind = "client"
        elif root in twins:
            kind = "twin"
        else:
            continue
        code_line = lines[node.lineno - 1].strip()
        calls.append(Call(page, start_line + node.lineno - 1, code_line, kind, node.attr))
    return sorted(set(calls), key=lambda c: (c.page, c.line, c.attr))


def twin_attributes() -> set[str]:
    """Every attribute any Twin class has, including ones set in __init__."""
    twin_module = sys.modules["cyberwave.twin"]
    base = twin_module.Twin
    names: set[str] = set()
    for _, cls in inspect.getmembers(twin_module, inspect.isclass):
        if not issubclass(cls, base):
            continue
        names.update(dir(cls))
        for klass in cls.__mro__:
            if klass.__module__.startswith("cyberwave"):
                names.update(SELF_ASSIGN.findall(inspect.getsource(klass)))
    # Sensor families (twin.camera, twin.lidar, ...) are resolved in
    # Twin.__getattr__, so they never show up in dir().
    base_module = sys.modules[base.__module__]
    names.update(getattr(base_module, "_SENSOR_FAMILY_ATTRS", ()))
    return names


def check(calls: list[Call]) -> list[Result]:
    from cyberwave import Cyberwave

    client = Cyberwave(api_key="offline-check")  # constructing needs no network
    twin_attrs = twin_attributes()
    results = []
    for call in calls:
        if call.kind == "client":
            if not hasattr(client, call.attr):
                results.append(Result(call, False, f"Cyberwave has no attribute '{call.attr}'"))
                continue
            value = getattr(client, call.attr)
            if _is_called(call) and not callable(value):
                results.append(
                    Result(call, False, f"cw.{call.attr} is a {type(value).__name__}, not callable")
                )
                continue
            results.append(Result(call, True, ""))
        else:
            ok = call.attr in twin_attrs
            reason = "" if ok else f"no Twin class has '{call.attr}'"
            results.append(Result(call, ok, reason))
    return results


def _is_called(call: Call) -> bool:
    return re.search(rf"\.{re.escape(call.attr)}\s*\(", call.code) is not None


def main() -> int:
    print(f"cyberwave {version('cyberwave')} vs {DOCS}\n")
    calls: list[Call] = []
    for page in PAGES:
        markdown = fetch(page)
        clients: set[str] = set()
        twins: set[str] = set()
        for start_line, code in python_blocks(markdown):
            try:
                calls.extend(find_calls(page, start_line, code, clients, twins))
            except SyntaxError as err:
                print(f"SKIP    {page}:{start_line + (err.lineno or 1) - 1}  not valid Python ({err.msg})")

    results = check(calls)
    broken = [r for r in results if not r.ok]
    for r in results:
        status = "OK    " if r.ok else "BROKEN"
        suffix = f"  <- {r.reason}" if r.reason else ""
        print(f"{status}  {r.call.page}:{r.call.line}  {r.call.code}{suffix}")

    print(f"\n{len(results)} calls checked, {len(broken)} broken")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
