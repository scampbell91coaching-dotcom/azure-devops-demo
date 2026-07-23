from app.app import create_app


def test_home_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["status"] == "ok"
    assert payload["message"] == "Flask app is running"
    assert payload["host"]


def test_health_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}
