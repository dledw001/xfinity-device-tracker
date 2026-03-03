import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RouterClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 30,
        fetch_retries: int = 2,
        retry_backoff_seconds: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.fetch_retries = fetch_retries
        self.retry_backoff_seconds = retry_backoff_seconds

        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            }
        )

    def _timeout(self) -> tuple[int, int]:
        return (self.connect_timeout_seconds, self.read_timeout_seconds)

    def _run_with_retries(self, fn):
        attempts = max(1, self.fetch_retries + 1)
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except requests.Timeout as exc:
                last_exc = exc
                if attempt == attempts:
                    break
                sleep_seconds = self.retry_backoff_seconds * attempt
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("router request failed")

    def login(self) -> str:
        def _login_once():
            return self.session.post(
                f"{self.base_url}/check.jst",
                data={
                    "username": self.username,
                    "password": self.password,
                    "locale": "false",
                },
                allow_redirects=False,
                timeout=self._timeout(),
            )

        r = self._run_with_retries(_login_once)

        if r.status_code != 302 or not r.headers.get("Location"):
            raise RuntimeError(f"Login failed: expected 302, got {r.status_code}")

        landing = r.headers["Location"]
        if not landing.startswith("http"):
            landing = f"{self.base_url}/{landing.lstrip('/')}"

        def _landing_once():
            return self.session.get(landing, timeout=self._timeout())

        self._run_with_retries(_landing_once)
        self.session.headers["Referer"] = landing
        return landing

    def fetch_connected_devices_html(self) -> str:
        def _fetch_once():
            self.login()

            page = self.session.get(
                f"{self.base_url}/connected_devices_computers.jst", timeout=self._timeout()
            )
            page.raise_for_status()
            return page.text

        html = self._run_with_retries(_fetch_once)
        if "connected_devices_computers" not in html and "device-info" not in html:
            raise RuntimeError(
                "Did not receive connected devices payload (unexpected HTML)."
            )

        return html
