"""Live deployment fingerprint tests; no secrets or provider calls."""
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as test_client:
        yield test_client


def test_health_is_public_on_hosted_demo_and_shows_valid_revision(client, monkeypatch):
    sha = "D86481A29BCE3B44785C11B312DB77798E9FA568"
    monkeypatch.setenv("RENDER_GIT_COMMIT", sha)
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "do-not-expose-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "do-not-expose-ai-key")
    result = client.get("/health")
    assert result.status_code == 200
    assert result.json() == {
        "status": "ok", "mode": "sandbox-only", "version": "0.2.0",
        "git_commit": sha.lower(),
    }
    assert "no-store" in result.headers["Cache-Control"]
    assert "do-not-expose" not in result.text
    assert "RENDER_GIT" not in result.text
    assert client.head("/health").status_code == 200
    # No shared judge credential is required to see deployment identity.
    assert client.get("/api/state").status_code == 503


@pytest.mark.parametrize("revision", [
    "", "unknown", "main", "a" * 39, "a" * 41,
    "g" * 40, "x" * 20 + "../private", "a" * 40 + "\nSECRET=1",
    "a" * 20 + "/".join(["unsafe", "text"]),
])
def test_invalid_commit_is_not_exposed(client, monkeypatch, revision):
    monkeypatch.setenv("RENDER_GIT_COMMIT", revision)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["git_commit"] is None
    assert "no-store" in response.headers["Cache-Control"]


def test_missing_commit_uses_null_not_a_guessed_version(client, monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    result = client.get("/health")
    assert result.json()["git_commit"] is None
    assert result.headers["x-content-type-options"] == "nosniff"
