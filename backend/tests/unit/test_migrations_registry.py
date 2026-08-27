"""Guards the Phase-1+ failure mode where a new domain's models.py is added but never
imported into migrations/env.py — autogenerate would then silently never see its tables.
"""

from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _BACKEND_DIR / "src"


def _module_path_for(models_file: Path) -> str:
    rel = models_file.relative_to(_BACKEND_DIR).with_suffix("")
    return ".".join(rel.parts)


def test_every_models_module_is_imported_in_env_py():
    env_py_source = (_BACKEND_DIR / "migrations" / "env.py").read_text()

    # src/models.py itself is the shared Base declaration (imported as `from src.models
    # import Base`, not `import src.models`) — excluded, not a domain models module.
    models_files = [
        *sorted(f for f in _SRC_DIR.rglob("models.py") if f != _SRC_DIR / "models.py"),
        _SRC_DIR / "idempotency.py",
    ]
    assert models_files, "expected at least one domain models.py plus src/idempotency.py"

    missing = []
    for f in models_files:
        module_path = _module_path_for(f)
        if f"import {module_path}" not in env_py_source:
            missing.append(module_path)

    assert not missing, f"migrations/env.py is missing explicit imports for: {missing}"
