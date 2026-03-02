import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

from db import connect, init_db, upsert_device, insert_observations

def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    if not s or s.upper() == "NA":
        return None
    return s


def norm_mac(mac: str) -> str:
    return mac.strip().upper()


def parse_rssi_dbm(s: Optional[str]) -> Optional[int]:
    s = clean_text(s)
    if not s:
        return None
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None

def find_device_name_text(host_td: Tag) -> Optional[str]:
    name_a = host_td.find(
        "a",
        class_=lambda c: isinstance(c, (str, list)) and (
            ("device-name" in c) if isinstance(c, str) else ("device-name" in c)
        ),
    )
    if not name_a:
        name_a = host_td.find("a")

    if not name_a:
        return None

    return clean_text(name_a.get_text(" ").strip())


def dl_to_map(device_info_div: Optional[Tag]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not device_info_div:
        return out

    dl = device_info_div.find("dl")
    if not dl:
        return out

    # Standard definition-list format: <dt>Label</dt><dd>Value</dd>
    dts = dl.find_all("dt")
    if dts:
        for dt in dts:
            label = clean_text(dt.get_text(" ", strip=True))
            if not label:
                continue
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            val = clean_text(dd.get_text(" ", strip=True))
            if val:
                out[label] = val
        if out:
            return out

    # Router legacy format: <dd><b>Label</b>...</dd>value_text<dd>...
    for dd in dl.find_all("dd"):
        label_tag = dd.find("b")
        label = clean_text(label_tag.get_text(" ", strip=True) if label_tag else dd.get_text(" ", strip=True))
        if not label:
            continue

        val_parts: List[str] = []
        sib = dd.next_sibling

        while sib is not None:
            if isinstance(sib, Tag) and sib.name == "dd":
                break
            if isinstance(sib, str):
                t = sib.strip()
                if t:
                    val_parts.append(t)
            elif isinstance(sib, Tag):
                t = sib.get_text(" ", strip=True)
                if t:
                    val_parts.append(t)
            sib = sib.next_sibling

        val = clean_text(" ".join(val_parts).strip() if val_parts else "")
        if val:
            out[label] = val

    return out


def parse_table(
    html: str,
    wrapper_div_id: str,
    status: str,
    *,
    host_header: str = "host-name",
    dhcp_header: str = "dhcp-or-reserved",
    rssi_header: Optional[str] = "rssi-level",
    connection_header: str = "connection-type",
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    wrapper = soup.find("div", id=wrapper_div_id)
    if not wrapper:
        return []

    table = wrapper.find("table", class_="data")
    if not table:
        return []

    rows: List[Dict[str, Any]] = []

    for tr in table.find_all("tr"):
        if tr.find("th") is not None:
            continue

        host_td = tr.find("td", attrs={"headers": host_header})
        if host_td is None:
            continue

        dhcp_td = tr.find("td", attrs={"headers": dhcp_header})
        rssi_td = tr.find("td", attrs={"headers": rssi_header}) if rssi_header else None
        conn_td = tr.find("td", attrs={"headers": connection_header})

        host_name = find_device_name_text(host_td)

        details = dl_to_map(host_td.find("div", class_="device-info"))
        mac_raw = details.get("MAC Address")
        if not mac_raw:
            continue
        mac = norm_mac(mac_raw)

        dhcp_mode = clean_text(dhcp_td.get_text(" ").strip()) if dhcp_td else None
        connection_type = clean_text(conn_td.get_text(" ").strip()) if conn_td else None
        rssi_dbm = parse_rssi_dbm(rssi_td.get_text(" ").strip()) if rssi_td else None

        ipv4 = clean_text(details.get("IPv4 Address"))
        ipv6_global = clean_text(details.get("IPv6 Address"))
        ipv6_linklocal = clean_text(details.get("Local Link IPv6 Address"))

        rows.append(
            {
                "status": status,
                "host_name": host_name,
                "mac": mac,
                "dhcp_mode": dhcp_mode,
                "rssi_dbm": rssi_dbm,
                "connection_type": connection_type,
                "ipv4": ipv4,
                "ipv6_global": ipv6_global,
                "ipv6_linklocal": ipv6_linklocal,
                "source": "connected_devices_computers.jst",
            }
        )

    return rows


def parse_connected_devices(html: str) -> List[Dict[str, Any]]:
    online = parse_table(html, "online-private", "online")
    offline = parse_table(
        html,
        "offline-private",
        "offline",
        host_header="offline-device-host-name",
        dhcp_header="offline-device-dhcp-reserve",
        rssi_header=None,
        connection_header="offline-device-conncection",
    )
    return online + offline

def ingest_html_snapshot(db_path: str, html: str) -> Dict[str, Any]:
    seen_at = now_iso_utc()
    rows = parse_connected_devices(html)

    conn = connect(db_path)
    init_db(conn)

    for r in rows:
        upsert_device(conn, mac=r["mac"], seen_at=seen_at, host_name=r.get("host_name"))
        r["seen_at"] = seen_at

    insert_observations(conn, rows)

    conn.commit()
    conn.close()

    online_count = sum(1 for r in rows if r["status"] == "online")
    offline_count = sum(1 for r in rows if r["status"] == "offline")

    return {"seen_at": seen_at, "online": online_count, "offline": offline_count, "total": len(rows)}
