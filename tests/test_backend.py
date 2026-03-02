import pytest

from backend import RouterClient


class FakeResponse:
    def __init__(self, status_code=200, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, post_response, get_responses):
        self.post_response = post_response
        self.get_responses = list(get_responses)
        self.verify = True
        self.headers = {}
        self.get_calls = []
        self.post_calls = []

    def post(self, *args, **kwargs):
        self.post_calls.append((args, kwargs))
        return self.post_response

    def get(self, *args, **kwargs):
        self.get_calls.append((args, kwargs))
        if not self.get_responses:
            raise AssertionError("Unexpected extra GET call.")
        return self.get_responses.pop(0)


def test_login_raises_when_router_does_not_redirect(monkeypatch):
    fake_session = FakeSession(FakeResponse(status_code=200), [])
    monkeypatch.setattr("backend.requests.Session", lambda: fake_session)

    client = RouterClient("https://10.0.0.1", "user", "pass")

    with pytest.raises(RuntimeError, match="Login failed"):
        client.login()


def test_login_uses_relative_redirect_and_updates_referer(monkeypatch):
    fake_session = FakeSession(
        FakeResponse(status_code=302, headers={"Location": "/index.jst"}),
        [FakeResponse(status_code=200, text="landing")],
    )
    monkeypatch.setattr("backend.requests.Session", lambda: fake_session)

    client = RouterClient("https://10.0.0.1", "user", "pass")
    landing = client.login()

    assert landing == "https://10.0.0.1/index.jst"
    assert fake_session.headers["Referer"] == "https://10.0.0.1/index.jst"
    assert len(fake_session.get_calls) == 1


def test_fetch_connected_devices_html_raises_on_unexpected_payload(monkeypatch):
    fake_session = FakeSession(
        FakeResponse(status_code=302, headers={"Location": "/index.jst"}),
        [
            FakeResponse(status_code=200, text="landing"),
            FakeResponse(
                status_code=200, text="<html><body>no devices here</body></html>"
            ),
        ],
    )
    monkeypatch.setattr("backend.requests.Session", lambda: fake_session)
    client = RouterClient("https://10.0.0.1", "user", "pass")

    with pytest.raises(RuntimeError, match="unexpected HTML"):
        client.fetch_connected_devices_html()


def test_fetch_connected_devices_html_returns_payload(monkeypatch):
    payload = "<div class='device-info'>connected_devices_computers</div>"
    fake_session = FakeSession(
        FakeResponse(status_code=302, headers={"Location": "/index.jst"}),
        [
            FakeResponse(status_code=200, text="landing"),
            FakeResponse(status_code=200, text=payload),
        ],
    )
    monkeypatch.setattr("backend.requests.Session", lambda: fake_session)
    client = RouterClient("https://10.0.0.1", "user", "pass")

    html = client.fetch_connected_devices_html()

    assert html == payload
