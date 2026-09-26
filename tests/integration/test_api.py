"""
Integration tests for FastAPI TTS Server endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from apps.tts_server.main import app
from apps.tts_server.inference import engine


@pytest.fixture(scope="module")
def client():
    # If model is not loaded in test, mock readiness for route test
    was_ready = engine.is_ready
    engine.is_ready = True
    with TestClient(app) as c:
        yield c
    engine.is_ready = was_ready


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "model_loaded" in data
    assert "vram_free_gb" in data


def test_ready_endpoint(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_voices_endpoint(client):
    response = client.get("/voices")
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    assert len(data["voices"]) > 0
    assert data["voices"][0]["id"] == "female_default"


def test_synthesize_empty_text_error(client):
    response = client.post("/synthesize", json={"text": "   ", "voice_id": "female_default"})
    assert response.status_code == 400
