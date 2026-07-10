// novelWriter Mobile — companion app
//
// This Progressive Web App is the mobile half of the cross-device workflow.
// It pulls the latest project snapshot from Google Drive (via OAuth),
// lets the user sketch notes anywhere, and queues them for the next sync.

const STORAGE = {
  NOTES: "novelwriter:notes",
  SNAPSHOT: "novelwriter:snapshot",
  TOKEN: "novelwriter:googleToken",
  PROJECT_ID: "novelwriter:projectId",
  DEVICE_ID: "novelwriter:deviceId",
  CLIENT_ID: "novelwriter:googleClientId"
};

const state = {
  connected: false,
  projectId: null,
  snapshot: null,
  notes: []
};

const SCOPES = ["https://www.googleapis.com/auth/drive.appdata"];

function ensureDeviceId() {
  let id = localStorage.getItem(STORAGE.DEVICE_ID);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
      `web-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    localStorage.setItem(STORAGE.DEVICE_ID, id);
  }
  return id;
}

function loadNotes() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE.NOTES)) || [];
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
      <div class="entry-meta">${new Date(note.createdAt).toLocaleString()} · ${note.id.slice(0, 8)}</div>
    `;
    list.appendChild(li);
  });
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}

async function sha256(value) {
  const encoder = new TextEncoder().encode(value);
  const buffer = await crypto.subtle.digest("SHA-256", encoder);
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function base64UrlEncode(buffer) {
  let str = "";
  for (const byte of new Uint8Array(buffer)) {
    str += String.fromCharCode(byte);
  }
  return btoa(str).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

async function startGoogleAuth() {
  const clientId = document.querySelector("[data-client-id]").value.trim();
  const projectId = document.querySelector("[data-project-id]").value.trim();
  if (!clientId) {
    setStatus("connect", "Informe o OAuth Client ID do Google.", "bad");
    return;
  }
  if (!projectId) {
    setStatus("connect", "Informe o Project UUID que aparece em Configurações do Projeto.", "bad");
    return;
  }

  localStorage.setItem(STORAGE.CLIENT_ID, clientId);
  localStorage.setItem(STORAGE.PROJECT_ID, projectId);
  ensureDeviceId();

  const verifier = base64UrlEncode(crypto.getRandomValues(new Uint8Array(48)));
  localStorage.setItem("novelwriter:codeVerifier", verifier);
  const challenge = base64UrlEncode(await sha256(verifier).then((hex) => {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i += 1) {
      out[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return out.buffer;
  }));

  const redirect = `${location.origin}${location.pathname}`;
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirect,
    response_type: "code",
    scope: SCOPES.join(" "),
    access_type: "offline",
    prompt: "consent",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: projectId
  });
  location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

async function exchangeCodeForToken(code, projectId) {
  const verifier = localStorage.getItem("novelwriter:codeVerifier");
  if (!verifier) {
    return;
  }
  const clientId = localStorage.getItem(STORAGE.CLIENT_ID);
  if (!clientId) {
    return;
  }
  const body = new URLSearchParams({
    client_id: clientId,
    code,
    code_verifier: verifier,
    grant_type: "authorization_code",
    redirect_uri: `${location.origin}${location.pathname}`
  });
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  if (!response.ok) {
    setStatus("connect", "Falha ao trocar o código por token.", "bad");
    return;
  }
  const data = await response.json();
  const token = {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: Date.now() + (data.expires_in * 1000)
  };
  localStorage.setItem(STORAGE.TOKEN, JSON.stringify(token));
  state.connected = true;
  state.projectId = projectId;
  setStatus("connect", "Conectado ao Google Drive.", "good");
  showSection("notes");
}

async function refreshToken() {
  const raw = localStorage.getItem(STORAGE.TOKEN);
  if (!raw) return null;
  const token = JSON.parse(raw);
  if (token.expiresAt > Date.now() + 60_000) {
    return token.accessToken;
  }
  const clientId = localStorage.getItem(STORAGE.CLIENT_ID);
  if (!clientId || !token.refreshToken) return null;
  const body = new URLSearchParams({
    client_id: clientId,
    refresh_token: token.refreshToken,
    grant_type: "refresh_token"
  });
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  if (!response.ok) return null;
  const data = await response.json();
  token.accessToken = data.access_token;
  token.expiresAt = Date.now() + (data.expires_in * 1000);
  localStorage.setItem(STORAGE.TOKEN, JSON.stringify(token));
  return token.accessToken;
}

async function callDrive(path, init = {}) {
  const token = await refreshToken();
  if (!token) throw new Error("Não conectado ao Google Drive.");
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

async function loadSnapshot() {
  const projectId = localStorage.getItem(STORAGE.PROJECT_ID);
  if (!projectId) {
    setStatus("notes", "Conecte-se primeiro.", "warn");
    return;
  }
  try {
    const encodedName = `nw-sync-head-${projectId}`.replace(/'/g, "\\'");
    const list = await callDrive(`/files?spaces=appDataFolder&q=name='${encodedName}' and trashed=false&fields=files(id,name)`);
    const data = await list.json();
    if (!data.files || data.files.length === 0) {
      setStatus("notes", "Projeto ainda não foi sincronizado a partir do desktop.", "warn");
      return;
    }
    const headResp = await callDrive(`/files/${data.files[0].id}?alt=media`);
    const manifestHash = (await headResp.text()).trim();
    const manifestResp = await callDrive(`/files?q=name='nw-sync-manifest-${manifestHash}' and trashed=false&fields=files(id)`);
    const manifestList = await manifestResp.json();
    if (!manifestList.files || manifestList.files.length === 0) {
      setStatus("notes", "Manifesto não encontrado no Drive.", "warn");
      return;
    }
    const manifestData = await (await callDrive(`/files/${manifestList.files[0].id}?alt=media`)).json();
    const files = manifestData.files || {};
    const sorted = Object.keys(files).slice(0, 5);
    let preview = "";
    for (const path of sorted) {
      const objResp = await callDrive(`/files?q=name='nw-sync-object-${files[path].hash}' and trashed=false&fields=files(id)`);
      const objList = await objResp.json();
      if (!objList.files || objList.files.length === 0) continue;
      const obj = await (await callDrive(`/files/${objList.files[0].id}?alt=media`)).text();
      preview += `### ${path}\n\n${obj.split("\n").slice(0, 12).join("\n")}\n\n`;
    }
    state.snapshot = preview;
    document.querySelector("[data-snapshot]").textContent = preview || "Nenhum documento legível encontrado.";
    setStatus("notes", "Snapshot carregado.", "good");
  } catch (err) {
    setStatus("notes", `Falha: ${err.message}`, "bad");
  }
}

function addNote() {
  const textarea = document.querySelector("[data-note-input]");
  const text = textarea.value.trim();
  if (!text) return;
  state.notes = loadNotes();
  state.notes.unshift({
    id: crypto.randomUUID ? crypto.randomUUID() : `n-${Date.now()}`,
    text,
    createdAt: new Date().toISOString()
  });
  persistNotes(state.notes);
  textarea.value = "";
  renderNotes();
}

function clearNotes() {
  if (!confirm("Apagar todas as notas deste dispositivo?")) return;
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
  URL.revokeObjectURL(url);
}

function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./service-worker.js").catch(() => {});
  }
  ensureDeviceId();
  state.notes = loadNotes();
  renderNotes();

  const params = new URLSearchParams(location.search);
  const code = params.get("code");
  const stateParam = params.get("state");
  if (code && stateParam) {
    exchangeCodeForToken(code, stateParam);
    history.replaceState(null, "", location.pathname);
    return;
  }

  const token = localStorage.getItem(STORAGE.TOKEN);
  if (token) {
    state.connected = true;
    state.projectId = localStorage.getItem(STORAGE.PROJECT_ID);
    showSection("notes");
  } else {
    showSection("connect");
  }

  document.querySelector("[data-connect-btn]").addEventListener("click", startGoogleAuth);
  document.querySelector("[data-load-snapshot]").addEventListener("click", loadSnapshot);
  document.querySelector("[data-add-note]").addEventListener("click", addNote);
  document.querySelector("[data-clear-notes]").addEventListener("click", clearNotes);
  document.querySelector("[data-export-notes]").addEventListener("click", exportNotes);
}

document.addEventListener("DOMContentLoaded", boot);
