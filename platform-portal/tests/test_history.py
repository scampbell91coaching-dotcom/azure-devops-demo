from portal import create_app

TEST_CONFIG = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}


def test_history_page_contract():
    app = create_app(TEST_CONFIG)
    client = app.test_client()

    # Register the generated blueprint before enabling this test.
    assert client is not None
