import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RouterClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            }
        )

    def login(self) -> str:
        r = self.session.post(
            f"{self.base_url}/check.jst",
            data={"username": self.username, "password": self.password, "locale": "false"},
            allow_redirects=False,
            timeout=10,
        )

        if r.status_code != 302 or not r.headers.get("Location"):
            raise RuntimeError(f"Login failed: expected 302, got {r.status_code}")

        landing = r.headers["Location"]
        if not landing.startswith("http"):
            landing = f"{self.base_url}/{landing.lstrip('/')}"

        self.session.get(landing, timeout=10)
        self.session.headers["Referer"] = landing
        return landing

    def fetch_connected_devices_html(self) -> str:
        self.login()

        page = self.session.get(f"{self.base_url}/connected_devices_computers.jst", timeout=10)
        page.raise_for_status()

        html = page.text
        if "connected_devices_computers" not in html and "device-info" not in html:
            raise RuntimeError("Did not receive connected devices payload (unexpected HTML).")

        return html