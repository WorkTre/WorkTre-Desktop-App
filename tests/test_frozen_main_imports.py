"""src/main.py must import as a frozen script, with no package-relative imports."""

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "main.py"


def test_main_source_has_no_relative_imports():
    text = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            segment = ast.get_source_segment(text, node) or ""
            raise AssertionError("relative import in src/main.py: %s" % segment)
    for line in text.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("from ."), stripped
        assert not stripped.startswith("import ."), stripped


def test_main_imports_execute_without_a_package_context():
    """Load every import in src/main.py the way PyInstaller runs that file."""
    script = textwrap.dedent(
        """
        import ast
        import sys
        import types
        from pathlib import Path

        root = Path(sys.argv[1])
        sys.path.insert(0, str(root))

        class _Dummy:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, *args, **kwargs):
                return _Dummy()

            def __getattr__(self, name):
                return _Dummy()

        webview = types.ModuleType("webview")
        webview.Window = _Dummy
        sys.modules["webview"] = webview
        source = (root / "src" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        namespace = {
            "__name__": "__main__",
            "__package__": None,
            "__file__": str(root / "src" / "main.py"),
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.ImportFrom) and node.level:
                segment = ast.get_source_segment(source, node)
                raise SystemExit("relative import: %s" % segment)
            segment = ast.get_source_segment(source, node)
            exec(segment, namespace)
        print("frozen-imports-ok")
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "frozen-imports-ok" in completed.stdout
