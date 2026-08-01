from portal import create_app


def test_history_page_is_available():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    response = app.test_client().get("/history")

    assert response.status_code == 200
    assert b"Platform History" in response.data
    assert b"platform-score-chart" in response.data
    assert b"latency-chart" in response.data
    assert b"restart-chart" in response.data


def test_history_dashboard_assets_are_available():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    client = app.test_client()

    assert client.get("/static/js/history_dashboard.js").status_code == 200
    assert client.get("/static/css/history_dashboard.css").status_code == 200
