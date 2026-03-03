from pathlib import Path

from ingest import clean_text, dl_to_map, parse_connected_devices, parse_rssi_dbm


def test_clean_text_normalizes_na_and_whitespace():
    assert clean_text("  hello  ") == "hello"
    assert clean_text("NA") is None
    assert clean_text("   ") is None
    assert clean_text(None) is None


def test_parse_rssi_dbm_extracts_integer():
    assert parse_rssi_dbm("-55 dBm") == -55
    assert parse_rssi_dbm("RSSI: -70") == -70
    assert parse_rssi_dbm("NA") is None


def test_dl_to_map_parses_dt_dd_pairs():
    html = """
    <div class="device-info">
      <dl>
        <dt>MAC Address</dt><dd>AA:BB:CC:DD:EE:FF</dd>
        <dt>IPv4 Address</dt><dd>10.0.0.2</dd>
      </dl>
    </div>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    parsed = dl_to_map(soup.find("div"))

    assert parsed["MAC Address"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["IPv4 Address"] == "10.0.0.2"


def test_dl_to_map_parses_legacy_dd_b_label_format():
    html = """
    <div class="device-info">
      <dl>
        <dd><b>MAC Address</b></dd> AA:BB:CC:DD:EE:FF
        <dd><b>IPv4 Address</b></dd> 10.0.0.2
      </dl>
    </div>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    parsed = dl_to_map(soup.find("div"))

    assert parsed["MAC Address"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["IPv4 Address"] == "10.0.0.2"


def test_parse_connected_devices_parses_online_and_offline_rows():
    html = """
    <div id="online-private">
      <table class="data">
        <tr><th>header</th></tr>
        <tr>
          <td headers="host-name">
            <a class="device-name">Laptop</a>
            <div class="device-info"><dl>
              <dt>MAC Address</dt><dd>AA:BB:CC:DD:EE:FF</dd>
              <dt>IPv4 Address</dt><dd>10.0.0.2</dd>
              <dt>IPv6 Address</dt><dd>2001:db8::1</dd>
              <dt>Local Link IPv6 Address</dt><dd>fe80::1</dd>
            </dl></div>
          </td>
          <td headers="dhcp-or-reserved">DHCP</td>
          <td headers="rssi-level">-55 dBm</td>
          <td headers="connection-type">WiFi</td>
        </tr>
      </table>
    </div>
    <div id="offline-private">
      <table class="data">
        <tr><th>header</th></tr>
        <tr>
          <td headers="offline-device-host-name">
            <a class="device-name">Tablet</a>
            <div class="device-info"><dl>
              <dt>MAC Address</dt><dd>11:22:33:44:55:66</dd>
            </dl></div>
          </td>
          <td headers="offline-device-dhcp-reserve">Reserved</td>
          <td headers="offline-device-conncection">WiFi</td>
        </tr>
      </table>
    </div>
    """

    rows = parse_connected_devices(html)
    assert len(rows) == 2

    online = next(r for r in rows if r["status"] == "online")
    offline = next(r for r in rows if r["status"] == "offline")

    assert online["host_name"] == "Laptop"
    assert online["mac"] == "AA:BB:CC:DD:EE:FF"
    assert online["ipv4"] == "10.0.0.2"
    assert online["rssi_dbm"] == -55
    assert offline["host_name"] == "Tablet"
    assert offline["mac"] == "11:22:33:44:55:66"


def test_parse_connected_devices_with_sample_html_snapshot():
    html = Path("sample.html").read_text(encoding="utf-8", errors="ignore")
    rows = parse_connected_devices(html)

    assert len(rows) == 87
    assert sum(1 for r in rows if r["status"] == "online") == 83
    assert sum(1 for r in rows if r["status"] == "offline") == 4
