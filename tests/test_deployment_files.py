from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_non_root_dynamic_port_startup() -> None:
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER orca" in content
    assert "--host 0.0.0.0" in content
    assert "${PORT:-8000}" in content
    assert ".[database,agents]" in content


def test_docker_context_excludes_credentials_and_frontend() -> None:
    entries = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert ".env" in entries
    assert ".env.*" in entries
    assert "frontend" in entries
