// novelWriter Mobile — companion app
// This Progressive Web App reads the latest project snapshot from Google Drive
// and keeps quick notes on the device.

const STORAGE = {
  NOTES: "novelwriter:notes",
  SNAPSHOT: "novelwriter:snapshot",
  TOKEN: "novelwriter:googleToken",
  PROJECT_ID: "novelwriter:projectId",
  DEVICE_ID: "novelwriter:deviceId",
  CLIENT_ID: "novelwriter:googleClientId",
  AUTH_VERSION: "novelwriter:googleAuthVersion"
};

const SCOPES = ["https://www.googleapis.com/auth/drive.appdata"];
const TOKEN_SKEW_MS = 60_000;
const GOOGLE_GSI_URL = "https://accounts.google.com/gsi/client";
const GOOGLE_AUTH_VERSION = "token-popup-v3";
let googleIdentityPromise = null;

const state = {
  connected: false,
  projectId: null,
  snapshot: null,
  notes: []
};

function ensureDeviceId() {
  let id = localStorage.getItem(STORAGE.DEVICE_ID);
  if (!id) {
    id = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `web-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    localStorage.setItem(STORAGE.DEVICE_ID, id);
  }
  return id;
}

function loadNotes() {
  try {
    const notes = JSON.parse(localStorage.getItem(STORAGE.NOTES) || "[]");
    return Array.isArray(notes)
      ? notes.filter((note) => note && typeof note.text === "string")
      : [];
  } catch (err) {
    return [];
  }
}

function persistNotes(notes) {
  localStorage.setItem(STORAGE.NOTES, JSON.stringify(notes));
}

function setStatus(target, text, kind = "info") {
  const el = document.querySelector(`[data-status="${target}"]`);
  if (!el) return;
  el.className = `status ${kind}`;
  el.textContent = text;
}

function showSection(name) {
  document.querySelectorAll(".section").forEach((sec) => {
    sec.classList.toggle("active", sec.dataset.section === name);
  });
}

function renderNotes() {
  const list = document.querySelector("[data-notes-list]");
  list.innerHTML = "";
  state.notes.forEach((note) => {
    const li = document.createElement("li");
    li.className = "list-item";
    li.innerHTML = `
      <div>${escapeHtml(note.text)}</div>
      <div class="entry-meta">${new Date(note.createdAt).toLocaleString()} · ${String(note.id || "").slice(0, 8)}</div>
    `;
    list.appendChild(li);
  });
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}

function migrateGoogleAuth() {
  if (localStorage.getItem(STORAGE.AUTH_VERSION) === GOOGLE_AUTH_VERSION) return;
  localStorage.removeItem(STORAGE.CLIENT_ID);
  localStorage.removeItem(STORAGE.TOKEN);
  localStorage.setItem(STORAGE.AUTH_VERSION, GOOGLE_AUTH_VERSION);
}

function loadGoogleIdentityServices() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (!googleIdentityPromise) {
    googleIdentityPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GOOGLE_GSI_URL;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => {
        googleIdentityPromise = null;
        reject(new Error("Could not load Google Identity Services."));
      };
      document.head.appendChild(script);
    });
  }
  return googleIdentityPromise.then(() => {
    if (!window.google?.accounts?.oauth2) {
      throw new Error("Google Identity Services is unavailable.");
    }
  });
}

function readToken() {
  try {
    const token = JSON.parse(localStorage.getItem(STORAGE.TOKEN) || "null");
    if (token && typeof token.accessToken === "string" && token.accessToken &&
        Number.isFinite(token.expiresAt)) {
      return token;
    }
  } catch (err) {
    // Remove malformed data below
  }
  localStorage.removeItem(STORAGE.TOKEN);
  return null;
}

function saveToken(response) {
  const expiresIn = Number(response.expires_in);
  if (typeof response.access_token !== "string" || !response.access_token ||
      !Number.isFinite(expiresIn) || expiresIn <= 0) {
    throw new Error("Google returned an invalid access token.");
  }
  const token = {
    accessToken: response.access_token,
    expiresAt: Date.now() + expiresIn * 1000
  };
  localStorage.setItem(STORAGE.TOKEN, JSON.stringify(token));
  return token;
}

async function requestAccessToken(clientId, prompt = "") {
  await loadGoogleIdentityServices();
  if (!clientId) throw new Error("Enter the Google OAuth Client ID first.");

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      callback(value);
    };
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPES.join(" "),
      callback: (response) => {
        if (response.error) {
          finish(reject, new Error(response.error_description || response.error));
          return;
        }
        try {
          finish(resolve, saveToken(response));
        } catch (err) {
          finish(reject, err);
        }
      },
      error_callback: (response) => {
        const message = response.type === "popup_closed"
          ? "Google authorisation was cancelled."
          : "Google authorisation popup could not be opened.";
        finish(reject, new Error(message));
      }
    });
    try {
      client.requestAccessToken(prompt ? { prompt } : {});
    } catch (err) {
      finish(reject, err);
    }
  });
}

async function startGoogleAuth() {
  const clientId = document.querySelector("[data-client-id]").value.trim();
  const projectId = document.querySelector("[data-project-id]").value.trim();
  if (!clientId) {
    setStatus("connect", "Enter the Google OAuth Client ID.", "bad");
    return;
  }
  if (!projectId) {
    setStatus("connect", "Enter the project UUID from Project Settings on the desktop.", "bad");
    return;
  }

  localStorage.setItem(STORAGE.PROJECT_ID, projectId);
  ensureDeviceId();
  setStatus("connect", "Opening Google authorisation…", "info");
  try {
    await requestAccessToken(clientId, "consent");
    localStorage.setItem(STORAGE.CLIENT_ID, clientId);
    state.connected = true;
    state.projectId = projectId;
    setStatus("connect", "Connected to Google Drive.", "good");
    showSection("notes");
  } catch (err) {
    setStatus("connect", `Could not connect: ${err.message}`, "bad");
  }
}

async function getAccessToken() {
  const token = readToken();
  if (token && token.expiresAt > Date.now() + TOKEN_SKEW_MS) return token.accessToken;
  const clientId = localStorage.getItem(STORAGE.CLIENT_ID);
  const refreshed = await requestAccessToken(clientId);
  return refreshed.accessToken;
}

function disconnectGoogle() {
  const token = readToken();
  if (token && window.google?.accounts?.oauth2) {
    window.google.accounts.oauth2.revoke(token.accessToken, () => {});
  }
  localStorage.removeItem(STORAGE.TOKEN);
  state.connected = false;
  showSection("connect");
  setStatus("connect", "Disconnected from Google Drive.", "info");
}

async function callDrive(path, init = {}) {
  const token = await getAccessToken();
  const headers = Object.assign({ Authorization: `Bearer ${token}` }, init.headers || {});
  const response = await fetch(`https://www.googleapis.com/drive/v3${path}`, {
    ...init,
    headers
  });
  if (!response.ok) {
    throw new Error(`Drive ${response.status}`);
  }
  return response;
}

async function findAppDataFile(name) {
  const escaped = name.replace(/'/g, "\\'");
  const query = encodeURIComponent(`name = '${escaped}' and trashed = false`);
  const response = await callDrive(
    `/files?spaces=appDataFolder&q=${query}&fields=files(id,name)`
  );
  const data = await response.json();
  return data.files && data.files.length ? data.files[0] : null;
}

async function loadSnapshot() {
  const projectId = localStorage.getItem(STORAGE.PROJECT_ID);
  if (!projectId) {
    setStatus("notes", "Connect first.", "warn");
    return;
  }
  try {
    const head = await findAppDataFile(`nw-sync-head-${projectId}`);
    if (!head) {
      setStatus("notes", "The project has not been synchronised from the desktop yet.", "warn");
      return;
    }
    const headResp = await callDrive(`/files/${head.id}?alt=media`);
    const manifestHash = (await headResp.text()).trim();
    const manifestFile = await findAppDataFile(`nw-sync-manifest-${manifestHash}`);
    if (!manifestFile) {
      setStatus("notes", "Manifest not found in Drive.", "warn");
      return;
    }
    const manifestData = await (await callDrive(`/files/${manifestFile.id}?alt=media`)).json();
    const files = manifestData.files || {};
    const sorted = Object.keys(files).slice(0, 5);
    let preview = "";
    for (const path of sorted) {
      const objectFile = await findAppDataFile(`nw-sync-object-${files[path].hash}`);
      if (!objectFile) continue;
      const obj = await (await callDrive(`/files/${objectFile.id}?alt=media`)).text();
      preview += `### ${path}\n\n${obj.split("\n").slice(0, 12).join("\n")}\n\n`;
    }
    state.snapshot = preview;
    localStorage.setItem(STORAGE.SNAPSHOT, preview);
    document.querySelector("[data-snapshot]").textContent = preview || "No readable document found.";
    setStatus("notes", "Snapshot loaded.", "good");
  } catch (err) {
    setStatus("notes", `Failed: ${err.message}`, "bad");
  }
}

function addNote() {
  const textarea = document.querySelector("[data-note-input]");
  const text = textarea.value.trim();
  if (!text) return;
  state.notes.unshift({
    id: typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `n-${Date.now()}`,
    text,
    createdAt: new Date().toISOString()
  });
  persistNotes(state.notes);
  textarea.value = "";
  renderNotes();
}

function clearNotes() {
  if (!confirm("Delete all notes on this device?")) return;
  state.notes = [];
  persistNotes(state.notes);
  renderNotes();
}

function exportNotes() {
  const blob = new Blob([JSON.stringify(state.notes, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "novelwriter-notes.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./service-worker.js", { updateViaCache: "none" })
      .then((registration) => registration.update())
      .catch(() => {});
  }
  migrateGoogleAuth();
  ensureDeviceId();
  state.notes = loadNotes();
  renderNotes();

  const savedClient = localStorage.getItem(STORAGE.CLIENT_ID);
  const savedProject = localStorage.getItem(STORAGE.PROJECT_ID);
  if (savedClient) document.querySelector("[data-client-id]").value = savedClient;
  if (savedProject) document.querySelector("[data-project-id]").value = savedProject;

  const savedSnapshot = localStorage.getItem(STORAGE.SNAPSHOT);
  if (savedSnapshot) document.querySelector("[data-snapshot]").textContent = savedSnapshot;

  const token = readToken();
  if (token && savedProject) {
    state.connected = true;
    state.projectId = savedProject;
    showSection("notes");
  } else {
    showSection("connect");
  }

  document.querySelector("[data-connect-btn]").addEventListener("click", startGoogleAuth);
  document.querySelector("[data-disconnect-btn]").addEventListener("click", disconnectGoogle);
  document.querySelector("[data-load-snapshot]").addEventListener("click", loadSnapshot);
  document.querySelector("[data-add-note]").addEventListener("click", addNote);
  document.querySelector("[data-clear-notes]").addEventListener("click", clearNotes);
  document.querySelector("[data-export-notes]").addEventListener("click", exportNotes);
}

document.addEventListener("DOMContentLoaded", boot);
