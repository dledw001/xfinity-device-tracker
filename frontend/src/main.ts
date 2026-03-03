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
  groups: string[];
};

type DevicesResponse = {
  seen_at: string;
  count: number;
  devices: Device[];
};

type DevicePatch = Partial<
  Pick<Device, "friendly_name" | "category" | "notes" | "is_hidden" | "is_tracked">
>;

type GroupSummary = {
  id: number;
  name: string;
  device_count: number;
};

type GroupsResponse = {
  count: number;
  groups: GroupSummary[];
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Missing #app mount node");
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api";
const API_TOKEN =
  (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim() || "changeme";

const STALE_SECONDS = 5 * 60;
const MAX_POLL_SECONDS = 300;
const UI_PREFS_KEY = "xfinity_ui_prefs";

const state = {
  devices: [] as Device[],
  groups: [] as GroupSummary[],
  seenAt: null as string | null,
  health: null as Health | null,
  includeArchived: false,
  onlyTracked: false,
  selectedGroupId: "all" as "all" | number,
  selectedMacs: new Set<string>(),
  loading: false,
  savingMac: null as string | null,
  groupActionKey: null as string | null,
  bulkAssigning: false,
  pollDelaySeconds: 60,
  error: null as string | null,
};

let pollTimer: number | null = null;

function headers(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Token": API_TOKEN,
  };
}

function loadUiPrefs(): void {
  try {
    const raw = window.localStorage.getItem(UI_PREFS_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as {
      includeArchived?: boolean;
      onlyTracked?: boolean;
    };
    state.includeArchived = Boolean(parsed.includeArchived);
    state.onlyTracked = Boolean(parsed.onlyTracked);
  } catch {
    // ignore invalid local storage values
  }
}

function persistUiPrefs(): void {
  window.localStorage.setItem(
    UI_PREFS_KEY,
    JSON.stringify({
      includeArchived: state.includeArchived,
      onlyTracked: state.onlyTracked,
    }),
  );
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

function getSeenAgeSeconds(device: Device): number | null {
  const millis = new Date(device.last_seen).getTime();
  if (Number.isNaN(millis)) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - millis) / 1000));
}

function isStale(device: Device): boolean {
  const age = getSeenAgeSeconds(device);
  return age !== null && age > STALE_SECONDS;
}

function isVisible(device: Device): boolean {
  if (!state.includeArchived && device.is_hidden) {
    return false;
  }
  if (state.onlyTracked && !device.is_tracked) {
    return false;
  }
  return true;
}

function visibleDevices(): Device[] {
  return state.devices.filter(isVisible);
}

function groupOptionsHtml(selected?: number): string {
  const opts = state.groups
    .map(
      (group) =>
        `<option value="${group.id}" ${selected === group.id ? "selected" : ""}>${escapeHtml(group.name)}</option>`,
    )
    .join("");
  return `<option value="">Choose group...</option>${opts}`;
}

function groupChipsHtml(groups: string[]): string {
  if (!groups.length) {
    return '<span class="chip chip-empty">No groups</span>';
  }
  return groups.map((name) => `<span class="chip">${escapeHtml(name)}</span>`).join("");
}

function staleBadgeHtml(device: Device): string {
  if (!isStale(device)) {
    return "";
  }
  const age = getSeenAgeSeconds(device);
  const mins = age === null ? "?" : String(Math.floor(age / 60));
  return `<span class="status-badge badge-stale">stale ${escapeHtml(mins)}m</span>`;
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
  const quickArchiveText = device.is_hidden ? "Unarchive" : "Archive";

  return `
    <tr data-mac="${mac}">
      <td>
        <input class="row-select" type="checkbox" data-mac="${mac}" ${state.selectedMacs.has(device.mac) ? "checked" : ""} />
      </td>
      <td>
        <div class="status-row">
          <span class="status-badge ${statusClass}">${escapeHtml(device.status)}</span>
          ${staleBadgeHtml(device)}
        </div>
      </td>
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
        <div class="quick-actions">
          <button type="button" class="btn-secondary row-archive-toggle" data-mac="${mac}">${quickArchiveText}</button>
        </div>
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
        <div class="group-section">
          <div class="chip-row">${groupChipsHtml(device.groups)}</div>
          <div class="group-actions" data-mac="${mac}">
            <select class="row-group-select">
              ${groupOptionsHtml()}
            </select>
            <button type="button" class="btn-secondary row-add-group">Add</button>
            <button type="button" class="btn-secondary row-remove-group">Remove</button>
          </div>
        </div>
      </td>
    </tr>
  `;
}

function render(): void {
  const rows = visibleDevices().map(uiRow).join("");
  const allVisibleSelected =
    visibleDevices().length > 0 && visibleDevices().every((d) => state.selectedMacs.has(d.mac));

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
          <label>
            <span class="muted">Group filter</span>
            <select id="group-filter">
              <option value="all" ${state.selectedGroupId === "all" ? "selected" : ""}>All groups</option>
              ${state.groups
                .map(
                  (group) =>
                    `<option value="${group.id}" ${state.selectedGroupId === group.id ? "selected" : ""}>${escapeHtml(group.name)}</option>`,
                )
                .join("")}
            </select>
          </label>
          <button id="refresh" class="btn-secondary" ${state.loading ? "disabled" : ""}>${state.loading ? "Refreshing..." : "Refresh"}</button>
        </div>
      </header>

      <section class="health-card">
        <div><strong>Service:</strong> ${state.health?.ok ? "OK" : "Degraded"}</div>
        <div><strong>Failures:</strong> ${state.health?.consecutive_failures ?? "-"}</div>
        <div><strong>Last ingest:</strong> ${escapeHtml(formatLocalDate(state.health?.last_ingest ?? null))}</div>
        <div><strong>Last error:</strong> ${escapeHtml(state.health?.last_error || "-")}</div>
        <div><strong>Error time:</strong> ${escapeHtml(formatLocalDate(state.health?.last_error_at ?? null))}</div>
        <div><strong>Next poll:</strong> ${state.pollDelaySeconds}s</div>
      </section>

      <section class="group-toolbar">
        <div class="group-create-row">
          <input id="new-group-name" type="text" placeholder="New group name" />
          <button id="create-group" class="btn-secondary">Create group</button>
        </div>
        <div class="group-bulk-row">
          <strong>Selected:</strong> ${state.selectedMacs.size}
          <select id="bulk-group-select">${groupOptionsHtml()}</select>
          <button id="bulk-assign" class="btn-secondary" ${state.bulkAssigning ? "disabled" : ""}>${state.bulkAssigning ? "Tagging..." : "Bulk tag selected"}</button>
          <button id="bulk-clear" class="btn-secondary">Clear selection</button>
        </div>
      </section>

      ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ""}

      <section class="table-wrap">
        <table>
          <thead>
            <tr>
              <th><input id="select-all" type="checkbox" ${allVisibleSelected ? "checked" : ""} /></th>
              <th>Status</th>
              <th>Name</th>
              <th>Host</th>
              <th>MAC</th>
              <th>IPs</th>
              <th>Connection</th>
              <th>Last seen</th>
              <th>Metadata + Groups</th>
            </tr>
          </thead>
          <tbody>
            ${rows || '<tr><td colspan="9" class="muted">No devices match current filters.</td></tr>'}
          </tbody>
        </table>
      </section>
    </main>
  `;

  bindUiEvents();
}

function bindUiEvents(): void {
  const archived = document.querySelector<HTMLInputElement>("#toggle-archived");
  archived?.addEventListener("change", () => {
    state.includeArchived = archived.checked;
    persistUiPrefs();
    render();
  });

  const tracked = document.querySelector<HTMLInputElement>("#toggle-tracked");
  tracked?.addEventListener("change", () => {
    state.onlyTracked = tracked.checked;
    persistUiPrefs();
    render();
  });

  const groupFilter = document.querySelector<HTMLSelectElement>("#group-filter");
  groupFilter?.addEventListener("change", async () => {
    state.selectedGroupId = groupFilter.value === "all" ? "all" : Number(groupFilter.value);
    await loadData();
    scheduleNextPoll();
  });

  const refresh = document.querySelector<HTMLButtonElement>("#refresh");
  refresh?.addEventListener("click", async () => {
    await loadData();
    scheduleNextPoll();
  });

  const selectAll = document.querySelector<HTMLInputElement>("#select-all");
  selectAll?.addEventListener("change", () => {
    for (const device of visibleDevices()) {
      if (selectAll.checked) {
        state.selectedMacs.add(device.mac);
      } else {
        state.selectedMacs.delete(device.mac);
      }
    }
    render();
  });

  document.querySelectorAll<HTMLButtonElement>(".row-archive-toggle").forEach((button) => {
    button.addEventListener("click", async () => {
      const mac = button.dataset.mac;
      if (!mac) {
        return;
      }
      const device = state.devices.find((d) => d.mac === mac);
      if (!device) {
        return;
      }
      await saveDevice(mac, { is_hidden: !device.is_hidden });
      scheduleNextPoll();
    });
  });

  document.querySelectorAll<HTMLInputElement>(".row-select").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const mac = checkbox.dataset.mac;
      if (!mac) {
        return;
      }
      if (checkbox.checked) {
        state.selectedMacs.add(mac);
      } else {
        state.selectedMacs.delete(mac);
      }
      render();
    });
  });

  const createGroup = document.querySelector<HTMLButtonElement>("#create-group");
  createGroup?.addEventListener("click", async () => {
    const input = document.querySelector<HTMLInputElement>("#new-group-name");
    const name = input?.value.trim() || "";
    if (!name) {
      state.error = "Group name is required";
      render();
      return;
    }

    try {
      await createGroupByName(name);
      if (input) {
        input.value = "";
      }
      await loadData();
      scheduleNextPoll();
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Failed to create group";
      render();
    }
  });

  const bulkAssign = document.querySelector<HTMLButtonElement>("#bulk-assign");
  bulkAssign?.addEventListener("click", async () => {
    const select = document.querySelector<HTMLSelectElement>("#bulk-group-select");
    const groupId = Number(select?.value || 0);
    if (!groupId) {
      state.error = "Choose a group for bulk tagging";
      render();
      return;
    }
    if (state.selectedMacs.size === 0) {
      state.error = "Select at least one device";
      render();
      return;
    }

    state.bulkAssigning = true;
    state.error = null;
    render();
    try {
      await bulkAssignGroup(groupId, [...state.selectedMacs]);
      await loadData();
      scheduleNextPoll();
    } catch (error) {
      state.error = error instanceof Error ? error.message : "Failed to bulk tag";
      render();
    } finally {
      state.bulkAssigning = false;
      render();
    }
  });

  const bulkClear = document.querySelector<HTMLButtonElement>("#bulk-clear");
  bulkClear?.addEventListener("click", () => {
    state.selectedMacs.clear();
    render();
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
      scheduleNextPoll();
    });
  });

  document.querySelectorAll<HTMLElement>(".group-actions").forEach((groupActions) => {
    const mac = groupActions.dataset.mac;
    if (!mac) {
      return;
    }
    const select = groupActions.querySelector<HTMLSelectElement>(".row-group-select");
    const addBtn = groupActions.querySelector<HTMLButtonElement>(".row-add-group");
    const removeBtn = groupActions.querySelector<HTMLButtonElement>(".row-remove-group");

    addBtn?.addEventListener("click", async () => {
      const groupId = Number(select?.value || 0);
      if (!groupId) {
        state.error = "Choose a group before adding";
        render();
        return;
      }
      await assignGroupToDevice(mac, groupId, "add");
      scheduleNextPoll();
    });

    removeBtn?.addEventListener("click", async () => {
      const groupId = Number(select?.value || 0);
      if (!groupId) {
        state.error = "Choose a group before removing";
        render();
        return;
      }
      await assignGroupToDevice(mac, groupId, "remove");
      scheduleNextPoll();
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

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status}: ${message}`);
  }
  return (await response.json()) as T;
}

async function loadHealth(): Promise<void> {
  state.health = await fetchJson<Health>(`${API_BASE_URL}/health`);
}

async function loadGroups(): Promise<void> {
  const payload = await fetchJson<GroupsResponse>(`${API_BASE_URL}/groups`, {
    headers: headers(),
  });
  state.groups = payload.groups;

  if (
    state.selectedGroupId !== "all" &&
    !state.groups.some((group) => group.id === state.selectedGroupId)
  ) {
    state.selectedGroupId = "all";
  }
}

async function loadDevices(): Promise<void> {
  const params = new URLSearchParams();
  if (state.selectedGroupId !== "all") {
    params.set("group_id", String(state.selectedGroupId));
  }
  const url = `${API_BASE_URL}/devices${params.toString() ? `?${params.toString()}` : ""}`;
  const payload = await fetchJson<DevicesResponse>(url, { headers: headers() });
  state.devices = payload.devices;
  state.seenAt = payload.seen_at;

  const visibleMacs = new Set(state.devices.map((d) => d.mac));
  for (const mac of [...state.selectedMacs]) {
    if (!visibleMacs.has(mac)) {
      state.selectedMacs.delete(mac);
    }
  }
}

async function createGroupByName(name: string): Promise<void> {
  await fetchJson<{ id: number; name: string }>(`${API_BASE_URL}/groups`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ name }),
  });
}

async function bulkAssignGroup(groupId: number, macs: string[]): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/groups/${groupId}/devices`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ macs }),
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`bulk ${response.status}: ${message}`);
  }
}

async function assignGroupToDevice(
  mac: string,
  groupId: number,
  action: "add" | "remove",
): Promise<void> {
  state.groupActionKey = `${action}:${mac}:${groupId}`;
  state.error = null;
  render();

  try {
    const response = await fetch(
      `${API_BASE_URL}/devices/${encodeURIComponent(mac)}/groups/${groupId}`,
      {
        method: action === "add" ? "POST" : "DELETE",
        headers: headers(),
      },
    );
    if (!response.ok) {
      const message = await response.text();
      throw new Error(`group ${response.status}: ${message}`);
    }
    await loadData();
  } catch (error) {
    state.error = error instanceof Error ? error.message : "Failed to update groups";
    render();
  } finally {
    state.groupActionKey = null;
    render();
  }
}

function computePollDelaySeconds(): number {
  const base = Math.max(1, state.health?.poll_seconds ?? 60);
  const failures = state.health?.consecutive_failures ?? 0;
  if (failures <= 1) {
    return base;
  }
  return Math.min(base * failures, MAX_POLL_SECONDS);
}

async function loadData(): Promise<void> {
  if (state.loading) {
    return;
  }
  state.loading = true;
  state.error = null;
  render();

  try {
    await loadGroups();
    await Promise.all([loadDevices(), loadHealth()]);
  } catch (error) {
    state.error = error instanceof Error ? error.message : "Failed to load data";
  } finally {
    state.loading = false;
    state.pollDelaySeconds = computePollDelaySeconds();
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

function scheduleNextPoll(): void {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
  }
  const delaySeconds = computePollDelaySeconds();
  state.pollDelaySeconds = delaySeconds;
  pollTimer = window.setTimeout(async () => {
    await loadData();
    scheduleNextPoll();
  }, delaySeconds * 1000);
}

loadUiPrefs();
void loadData().then(() => {
  scheduleNextPoll();
});