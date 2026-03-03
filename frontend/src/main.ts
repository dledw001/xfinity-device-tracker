import "./style.css";

type Health = {
  ok: boolean;
  last_ingest: string | null;
  last_error: string | null;
  last_error_at: string | null;
  consecutive_failures: number;
  poll_seconds: number;
};

type Device = {
  mac: string;
  status: "online" | "offline";
  host_name: string | null;
  dhcp_mode: string | null;
  rssi_dbm: number | null;
  connection_type: string | null;
  ipv4: string | null;
  ipv6_global: string | null;
  ipv6_linklocal: string | null;
  friendly_name: string | null;
  category: string | null;
  notes: string | null;
  is_hidden: boolean;
  is_tracked: boolean;
  last_host_name: string | null;
  first_seen: string;
  last_seen: string;
  display_name: string;
};

type DevicesResponse = {
  seen_at: string;
  count: number;
  devices: Device[];
};

type DevicePatch = Partial<
  Pick<Device, "friendly_name" | "category" | "notes" | "is_hidden" | "is_tracked">
>;

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Missing #app mount node");
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api";
const API_TOKEN = (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim() || "changeme";

const state = {
  devices: [] as Device[],
  seenAt: null as string | null,
  health: null as Health | null,
  includeArchived: false,
  onlyTracked: false,
  loading: false,
  savingMac: null as string | null,
  error: null as string | null,
};

let pollTimer: number | null = null;

function headers(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Token": API_TOKEN,
  };
}

function escapeHtml(value: string | null | undefined): string {
  const text = value ?? "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatLocalDate(iso: string | null): string {
  if (!iso) {
    return "-";
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function filteredDevices(): Device[] {
  return state.devices.filter((device) => {
    if (!state.includeArchived && device.is_hidden) {
      return false;
    }
    if (state.onlyTracked && !device.is_tracked) {
      return false;
    }
    return true;
  });
}

function uiRow(device: Device): string {
  const name = escapeHtml(device.display_name);
  const host = escapeHtml(device.host_name || device.last_host_name || "-");
  const ipv4 = escapeHtml(device.ipv4 || "-");
  const ipv6 = escapeHtml(device.ipv6_global || device.ipv6_linklocal || "-");
  const conn = escapeHtml(device.connection_type || "-");
  const mac = escapeHtml(device.mac);
  const statusClass = device.status === "online" ? "badge-online" : "badge-offline";
  const saving = state.savingMac === device.mac;

  return `
    <tr data-mac="${mac}">
      <td><span class="status-badge ${statusClass}">${escapeHtml(device.status)}</span></td>
      <td><strong>${name}</strong></td>
      <td>${host}</td>
      <td><code>${mac}</code></td>
      <td>
        <div>${ipv4}</div>
        <div class="muted">${ipv6}</div>
      </td>
      <td>${conn}</td>
      <td>${escapeHtml(formatLocalDate(device.last_seen))}</td>
      <td>
        <form class="row-edit-form">
          <div class="field-grid">
            <label>
              <span>Friendly name</span>
              <input name="friendly_name" type="text" value="${escapeHtml(device.friendly_name)}" />
            </label>
            <label>
              <span>Category</span>
              <input name="category" type="text" value="${escapeHtml(device.category)}" />
            </label>
            <label class="field-wide">
              <span>Notes</span>
              <input name="notes" type="text" value="${escapeHtml(device.notes)}" />
            </label>
            <label class="checkbox-row">
              <input name="is_hidden" type="checkbox" ${device.is_hidden ? "checked" : ""} />
              <span>Archived</span>
            </label>
            <label class="checkbox-row">
              <input name="is_tracked" type="checkbox" ${device.is_tracked ? "checked" : ""} />
              <span>Tracked</span>
            </label>
          </div>
          <button type="submit" class="btn-save" ${saving ? "disabled" : ""}>${saving ? "Saving..." : "Save"}</button>
        </form>
      </td>
    </tr>
  `;
}

function render(): void {
  const rows = filteredDevices().map(uiRow).join("");
  app.innerHTML = `
    <main class="shell">
      <header class="topbar">
        <div>
          <h1>Network Devices</h1>
          <p class="muted">Router snapshot: ${escapeHtml(formatLocalDate(state.seenAt))}</p>
        </div>
        <div class="controls">
          <label class="checkbox-row">
            <input id="toggle-archived" type="checkbox" ${state.includeArchived ? "checked" : ""} />
            <span>Include archived</span>
          </label>
          <label class="checkbox-row">
            <input id="toggle-tracked" type="checkbox" ${state.onlyTracked ? "checked" : ""} />
            <span>Tracked only</span>
          </label>
          <button id="refresh" class="btn-secondary" ${state.loading ? "disabled" : ""}>${state.loading ? "Refreshing..." : "Refresh"}</button>
        </div>
      </header>

      <section class="health-card">
        <div><strong>Service:</strong> ${state.health?.ok ? "OK" : "Degraded"}</div>
        <div><strong>Failures:</strong> ${state.health?.consecutive_failures ?? "-"}</div>
        <div><strong>Last ingest:</strong> ${escapeHtml(formatLocalDate(state.health?.last_ingest ?? null))}</div>
        <div><strong>Last error:</strong> ${escapeHtml(state.health?.last_error || "-")}</div>
      </section>

      ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ""}

      <section class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Name</th>
              <th>Host</th>
              <th>MAC</th>
              <th>IPs</th>
              <th>Connection</th>
              <th>Last seen</th>
              <th>Metadata</th>
            </tr>
          </thead>
          <tbody>
            ${rows || '<tr><td colspan="8" class="muted">No devices match current filters.</td></tr>'}
          </tbody>
        </table>
      </section>
    </main>
  `;

  const archived = document.querySelector<HTMLInputElement>("#toggle-archived");
  archived?.addEventListener("change", () => {
    state.includeArchived = archived.checked;
    render();
  });

  const tracked = document.querySelector<HTMLInputElement>("#toggle-tracked");
  tracked?.addEventListener("change", () => {
    state.onlyTracked = tracked.checked;
    render();
  });

  const refresh = document.querySelector<HTMLButtonElement>("#refresh");
  refresh?.addEventListener("click", async () => {
    await loadData();
  });

  document.querySelectorAll<HTMLFormElement>(".row-edit-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const tr = form.closest("tr");
      const mac = tr?.dataset.mac;
      if (!mac) {
        return;
      }

      const data = new FormData(form);
      const patch: DevicePatch = {
        friendly_name: normalizeOptionalText(data.get("friendly_name")),
        category: normalizeOptionalText(data.get("category")),
        notes: normalizeOptionalText(data.get("notes")),
        is_hidden: data.get("is_hidden") === "on",
        is_tracked: data.get("is_tracked") === "on",
      };

      await saveDevice(mac, patch);
    });
  });
}

function normalizeOptionalText(value: FormDataEntryValue | null): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

async function loadHealth(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`health ${response.status}`);
  }
  state.health = (await response.json()) as Health;
}

async function loadDevices(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/devices`, { headers: headers() });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`devices ${response.status}: ${message}`);
  }
  const payload = (await response.json()) as DevicesResponse;
  state.devices = payload.devices;
  state.seenAt = payload.seen_at;
}

async function loadData(): Promise<void> {
  state.loading = true;
  state.error = null;
  render();

  try {
    await Promise.all([loadDevices(), loadHealth()]);
  } catch (error) {
    state.error = error instanceof Error ? error.message : "Failed to load data";
  } finally {
    state.loading = false;
    render();
  }
}

async function saveDevice(mac: string, patch: DevicePatch): Promise<void> {
  state.savingMac = mac;
  state.error = null;
  render();

  try {
    const response = await fetch(`${API_BASE_URL}/devices/${encodeURIComponent(mac)}`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(patch),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(`patch ${response.status}: ${message}`);
    }
    await loadData();
  } catch (error) {
    state.error = error instanceof Error ? error.message : "Failed to save";
    render();
  } finally {
    state.savingMac = null;
    render();
  }
}

function startPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
  }
  pollTimer = window.setInterval(() => {
    void loadData();
  }, 60000);
}

void loadData();
startPolling();
