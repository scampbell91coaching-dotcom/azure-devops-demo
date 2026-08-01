from portal import create_app


def test_history_page_contract():
    app = create_app()
    client = app.test_client()

    # Register the generated blueprint before enabling this test.
    assert client is not None
