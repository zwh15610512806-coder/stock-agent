from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import sources


def test_sources_status_reports_config_and_cache_without_network(tmp_path, monkeypatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("sources status must not access external network")

    monkeypatch.setattr("socket.create_connection", fail_network)

    app = FastAPI()
    app.state.sources_settings = SimpleNamespace(
        deepseek_api_key="deepseek-key",
        volcengine_api_key="",
        tencentcloud_secret_id="secret-id",
        tencentcloud_secret_key="",
    )
    app.state.sources_cache_path = tmp_path / "market_cache.sqlite3"
    app.include_router(sources.router)
    client = TestClient(app)

    response = client.get("/api/sources/status")

    assert response.status_code == 200
    body = response.json()
    key_status = {item["name"]: item for item in body["key_status"]}
    assert key_status["DeepSeek"]["configured"] is True
    assert key_status["Volcengine OCR"]["configured"] is False
    assert key_status["Tencent OCR"]["configured"] is False
    assert body["cache"]["writable"] is True
    assert body["cache"]["path"] == str(tmp_path)
    assert {item["source"] for item in body["free_data_sources"]} >= {
        "tencent-free-delayed",
        "Yahoo Finance/free delayed fallback",
        "akshare-eastmoney-free",
    }
    assert body["disclaimer"]
