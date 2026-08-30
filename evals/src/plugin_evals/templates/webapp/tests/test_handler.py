from src.handler import upload

class Req:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}

def test_upload_requires_auth():
    assert upload(Req(b"x"))["status"] == 401

def test_upload_accepts():
    assert upload(Req(b"x", {"X-Auth": "t"}))["status"] == 202
