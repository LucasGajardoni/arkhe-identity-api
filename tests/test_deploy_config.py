from pathlib import Path

from app.core.config import Settings


def test_start_script_is_fail_fast_and_execs_uvicorn():
    script = Path("scripts/start.sh").read_text(encoding="utf-8")
    assert "set -eu" in script
    assert "alembic upgrade head" in script
    assert "if ! alembic" not in script
    assert "exec uvicorn" in script
    assert "--proxy-headers" in script
    assert "--forwarded-allow-ips" in script


def test_dockerignore_excludes_sensitive_and_local_files():
    ignored = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {
        ".git",
        ".env",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "*.db",
        "models",
        "tests",
    } <= ignored


def test_dockerfile_requires_64_bit_python_and_checks_readiness():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "struct.calcsize('P') * 8 == 64" in dockerfile
    assert "pip install -r requirements.txt" in dockerfile
    assert "USER arkhe" in dockerfile
    assert "http://127.0.0.1:8000/ready" in dockerfile


def test_api_docs_setting_defaults_to_compatible_enabled():
    assert Settings(environment="test").enable_api_docs is True
