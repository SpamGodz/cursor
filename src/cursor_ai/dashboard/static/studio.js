const $ = (id) => document.getElementById(id);

let chatId = null;
let selectedEvalRunId = null;

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

  // Evals
  $("refreshEvals").addEventListener("click", refreshEvals);
  $("newSuite").addEventListener("click", createSuite);
  $("runEval").addEventListener("click", runEval);
  $("addCase").addEventListener("click", addCase);
  $("approveEval").addEventListener("click", approveSelectedEval);
  $("suiteSelect").addEventListener("change", loadCasesForSelectedSuite);

  await refreshEvals();
});

async function refreshEvals() {
  const baseline = await fetch("/api/evals/baseline").then((r) => r.json());
  $("baselineSnapshot").textContent = baseline.baseline_snapshot_id || "-";

  const suitesResp = await fetch("/api/evals/suites").then((r) => r.json());
  const suites = suitesResp.suites || [];
  const sel = $("suiteSelect");
  sel.innerHTML = "";
  for (const s of suites) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    sel.appendChild(opt);
  }
  if (suites.length) sel.value = suites[0].id;
  await loadCasesForSelectedSuite();

  const runsResp = await fetch("/api/evals/runs").then((r) => r.json());
  renderEvalRuns(runsResp.runs || []);

  const improvementsResp = await fetch("/api/evals/improvements").then((r) => r.json());
  // optional: could render improvements history later.
  void improvementsResp;
}

async function createSuite() {
  const name = prompt("Suite name?");
  if (!name) return;
  await fetch("/api/evals/suites", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await refreshEvals();
}

async function loadCasesForSelectedSuite() {
  const suiteId = $("suiteSelect").value;
  if (!suiteId) return;
  const resp = await fetch(`/api/evals/suites/${suiteId}/cases`).then((r) => r.json());
  const cases = resp.cases || [];
  // Show a quick hint in summary area.
  $("evalSummary").textContent = `${cases.length} cases in selected suite.`;
}

async function addCase() {
  const suiteId = $("suiteSelect").value;
  const title = $("caseTitle").value.trim();
  const goal = $("caseGoal").value.trim();
  const rubric = $("caseRubric").value.trim() || null;
  if (!suiteId || !title || !goal) return;
  await fetch(`/api/evals/suites/${suiteId}/cases`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title, goal, rubric }),
  });
  $("caseTitle").value = "";
  $("caseGoal").value = "";
  $("caseRubric").value = "";
  await loadCasesForSelectedSuite();
}

async function runEval() {
  const suiteId = $("suiteSelect").value;
  if (!suiteId) return;
  const workspace = $("workspace").textContent;
  const label = prompt("Snapshot label? (optional)") || null;
  const resp = await fetch("/api/evals/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ suite_id: suiteId, workspace, label }),
  }).then((r) => r.json());
  alert(`Eval started: ${resp.eval_run_id}. Refresh in a moment to see results.`);
  await refreshEvals();
}

function renderEvalRuns(runs) {
  const root = $("evalRuns");
  root.innerHTML = "";
  for (const r of runs) {
    const el = document.createElement("div");
    el.className = "listitem";
    if (r.id === selectedEvalRunId) el.classList.add("active");
    const title = `Eval ${r.id.slice(0, 8)} (${r.status})`;
    const meta = `${r.cases_done || 0}/${r.cases_total || 0} cases`;
    el.innerHTML = `
      <div class="listtitle"></div>
      <div class="listmeta"></div>
      <div class="chiprow">
        <div class="chip">avg dur: ${r.avg_duration_s ? r.avg_duration_s.toFixed(2) + "s" : "-"}</div>
        <div class="chip">avg tokens: ${r.avg_total_tokens ? Math.round(r.avg_total_tokens) : "-"}</div>
        <div class="chip">tools: ${r.total_tool_calls ?? 0}</div>
      </div>
    `;
    el.querySelector(".listtitle").textContent = title;
    el.querySelector(".listmeta").textContent = meta;
    el.onclick = async () => {
      selectedEvalRunId = r.id;
      $("selectedEvalRun").textContent = selectedEvalRunId;
      $("approveEval").disabled = r.status !== "completed";
      renderEvalRuns(runs);
      await loadEvalResults(selectedEvalRunId);
    };
    root.appendChild(el);
  }
}

async function loadEvalResults(evalRunId) {
  const run = await fetch(`/api/evals/runs/${evalRunId}`).then((r) => r.json());
  const res = await fetch(`/api/evals/runs/${evalRunId}/results`).then((r) => r.json());
  $("evalSummary").textContent = `Status: ${run.status}. Snapshot: ${run.snapshot_id}.`;
  const root = $("evalResults");
  root.innerHTML = "";
  for (const item of res.results || []) {
    const el = document.createElement("div");
    el.className = "listitem";
    const verdict = item.reviewed_verdict || "unreviewed";
    el.innerHTML = `
      <div class="listtitle"></div>
      <div class="listmeta"></div>
      <div class="chiprow"></div>
      <details>
        <summary class="subtle">Output</summary>
        <pre class="log" style="height: 160px">${escapeHtml(item.output || item.error || "")}</pre>
      </details>
      <div class="row">
        <button class="btn">Mark pass</button>
        <button class="btn danger">Mark fail</button>
      </div>
    `;
    el.querySelector(".listtitle").textContent = item.title;
    el.querySelector(".listmeta").textContent = verdict;
    const chips = el.querySelector(".chiprow");
    chips.appendChild(mkChip(`status: ${item.status}`, item.status === "needs_review" ? "chip" : "chip bad"));
    chips.appendChild(mkChip(`dur: ${item.duration_s ? item.duration_s.toFixed(2) + "s" : "-"}`, "chip"));
    chips.appendChild(mkChip(`tokens: ${item.total_tokens ?? "-"}`, "chip"));
    chips.appendChild(mkChip(`tools: ${item.tool_calls ?? 0}`, "chip"));

    const [passBtn, failBtn] = el.querySelectorAll("button");
    passBtn.onclick = async () => {
      await reviewCase(evalRunId, item.case_id, "pass");
      await loadEvalResults(evalRunId);
    };
    failBtn.onclick = async () => {
      await reviewCase(evalRunId, item.case_id, "fail");
      await loadEvalResults(evalRunId);
    };
    root.appendChild(el);
  }
}

function mkChip(text, cls) {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = text;
  return d;
}

async function reviewCase(evalRunId, caseId, verdict) {
  const notes = prompt("Notes (optional)") || null;
  await fetch(`/api/evals/runs/${evalRunId}/cases/${caseId}/review`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ verdict, notes }),
  });
}

async function approveSelectedEval() {
  if (!selectedEvalRunId) return;
  const notes = $("approveNotes").value.trim() || null;
  const resp = await fetch(`/api/evals/runs/${selectedEvalRunId}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ notes }),
  }).then((r) => r.json());
  alert(`Approved. Baseline snapshot is now: ${resp.baseline_snapshot_id}`);
  $("approveNotes").value = "";
  await refreshEvals();
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

