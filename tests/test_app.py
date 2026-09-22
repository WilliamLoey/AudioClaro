import importlib


def load_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ADMIN_TOKEN", "segredo-teste")
    import app as app_module

    app_module = importlib.reload(app_module)
    app_module.app.config.update(TESTING=True)
    return app_module.app


def valid_payload():
    return {
        "participant_code": "P1",
        "activity": "Profissional autônomo",
        "audios_per_day": "6 a 10",
        "recent_episode": "Precisou ouvir novamente para confirmar um prazo.",
        "impact": "Gastou tempo e respondeu com atraso.",
        "preference": "sim",
        "feedback": "As tarefas ficaram claras.",
        "second_action": "sim",
        "confidence": "sim",
        "concern": "Quer poder apagar os dados.",
        "notes": "",
        "consent": True,
        "website": "",
    }


def test_complete_validation_flow(tmp_path, monkeypatch):
    flask_app = load_app(tmp_path, monkeypatch)
    client = flask_app.test_client()

    created = client.post("/api/responses", json=valid_payload())
    assert created.status_code == 201
    record_id = created.get_json()["id"]

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.get_json() == {
        "total": 1,
        "problem_percent": 100,
        "preference_percent": 100,
        "action_percent": 100,
        "confidence_percent": 100,
    }

    unauthorized = client.get("/api/responses")
    assert unauthorized.status_code == 401

    headers = {"X-Admin-Token": "segredo-teste"}
    listed = client.get("/api/responses", headers=headers)
    assert listed.status_code == 200
    assert listed.get_json()["total"] == 1

    exported = client.get("/api/export.csv", headers=headers)
    assert exported.status_code == 200
    assert "P1" in exported.get_data(as_text=True)

    deleted = client.delete(f"/api/responses/{record_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/api/stats").get_json()["total"] == 0


def test_rejects_invalid_payload(tmp_path, monkeypatch):
    flask_app = load_app(tmp_path, monkeypatch)
    response = flask_app.test_client().post("/api/responses", json={})
    assert response.status_code == 400
    assert "error" in response.get_json()

