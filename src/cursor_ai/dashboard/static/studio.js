const $ = (id) => document.getElementById(id);

let chatId = null;

function setStatus(text) {
  $("prefsStatus").textContent = text;
  setTimeout(() => {
    if ($("prefsStatus").textContent === text) $("prefsStatus").textContent = "";
  }, 2000);
}

async function loadPrefs() {
  const prefs = await fetch("/api/preferences").then((r) => r.json());
  $("prefSystemPrompt").value = prefs.system_prompt || "";
  $("prefMaxSteps").value = prefs.max_steps || 24;
  $("prefEnableWrite").checked = !!prefs.enable_write;
  $("prefModel").value = prefs.model || "";
  $("prefBaseUrl").value = prefs.base_url || "";
}

async function savePrefs() {
  const payload = {
    system_prompt: $("prefSystemPrompt").value,
    max_steps: parseInt($("prefMaxSteps").value || "24", 10),
    enable_write: $("prefEnableWrite").checked,
    model: $("prefModel").value.trim() || null,
    base_url: $("prefBaseUrl").value.trim() || null,
  };
  await fetch("/api/preferences", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then((r) => r.json());
  setStatus("Saved");
}

function renderFeatureCard(f) {
  const el = document.createElement("div");
  el.className = "carditem";
  el.innerHTML = `
    <div class="cardtitle"></div>
    <div class="carddesc"></div>
    <div class="cardactions"></div>
  `;
  el.querySelector(".cardtitle").textContent = f.title;
  el.querySelector(".carddesc").textContent = f.description || "";

  const actions = el.querySelector(".cardactions");
  const mkBtn = (label, next) => {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = label;
    b.onclick = async () => {
      await fetch(`/api/features/${f.id}/move`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      await loadFeatures();
    };
    actions.appendChild(b);
  };

  if (f.status !== "backlog") mkBtn("←", f.status === "done" ? "in_progress" : "backlog");
  if (f.status !== "done") mkBtn("→", f.status === "backlog" ? "in_progress" : "done");

  const runBtn = document.createElement("button");
  runBtn.className = "btn primary";
  runBtn.textContent = "Run";
  runBtn.onclick = async () => {
    // Kick off an agent run using current workspace and preferences.
    const workspace = $("workspace").textContent;
    await fetch("/api/runs/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: `Feature: ${f.title}\n\n${f.description || ""}\n\nImplement this feature in the repo.`,
        workspace,
      }),
    });
    alert("Run started. Switch to Monitor to view logs.");
  };
  actions.appendChild(runBtn);

  return el;
}

async function loadFeatures() {
  const data = await fetch("/api/features").then((r) => r.json());
  const cols = {
    backlog: $("colBacklog"),
    in_progress: $("colProgress"),
    done: $("colDone"),
  };
  for (const k of Object.keys(cols)) cols[k].innerHTML = "";
  for (const f of data.features || []) {
    const col = cols[f.status] || cols.backlog;
    col.appendChild(renderFeatureCard(f));
  }
}

async function addFeature() {
  const title = $("featureTitle").value.trim();
  const description = $("featureDesc").value;
  if (!title) return;
  await fetch("/api/features", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title, description }),
  });
  $("featureTitle").value = "";
  $("featureDesc").value = "";
  await loadFeatures();
}

function addBubble(role, content) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.textContent = content;
  $("chatLog").appendChild(el);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
}

async function ensureChat() {
  if (chatId) return chatId;
  const resp = await fetch("/api/chat/start", { method: "POST" }).then((r) => r.json());
  chatId = resp.chat_id;
  $("chatId").textContent = chatId;
  $("chatLog").innerHTML = "";
  return chatId;
}

async function loadChat() {
  if (!chatId) return;
  const resp = await fetch(`/api/chat/${chatId}`).then((r) => r.json());
  $("chatLog").innerHTML = "";
  for (const m of resp.messages || []) {
    addBubble(m.role, m.content);
  }
}

async function sendChat() {
  const msg = $("chatInput").value.trim();
  if (!msg) return;
  await ensureChat();
  $("chatInput").value = "";
  addBubble("user", msg);
  const workspace = $("workspace").textContent;
  const resp = await fetch(`/api/chat/${chatId}/send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message: msg, workspace }),
  }).then((r) => r.json());
  addBubble("assistant", resp.assistant || "");
}

window.addEventListener("DOMContentLoaded", async () => {
  $("savePrefs").addEventListener("click", savePrefs);
  $("addFeature").addEventListener("click", addFeature);
  $("newChat").addEventListener("click", async () => {
    chatId = null;
    await ensureChat();
  });
  $("chatSend").addEventListener("click", sendChat);
  $("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChat();
  });

  await loadPrefs();
  await loadFeatures();
  await ensureChat();
  await loadChat();
});

