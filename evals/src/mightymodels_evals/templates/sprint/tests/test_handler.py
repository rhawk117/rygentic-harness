from src.handler import upload

def test_handler_enforces_limit():
    assert upload(b"x", 5)["status"] == 202
    assert upload(b"x", 31)["status"] == 429
