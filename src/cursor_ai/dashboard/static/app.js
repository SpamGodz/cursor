const $ = (id) => document.getElementById(id);

let currentRunId = null;
let timerInterval = null;
let startedAtMs = null;
let es = null;

function fmtDuration(s) {
  if (s === null || s === undefined) return "-";
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m.toString().padStart(2, "0")}:${r.toString().padStart(2, "0")}`;
}

function setTimerRunning(isRunning) {
  if (timerInterval) clearInterval(timerInterval);
  if (!isRunning) {
    $("timer").textContent = "00:00";
    timerInterval = null;
    startedAtMs = null;
    return;
  }
  startedAtMs = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startedAtMs) / 1000);
    $("timer").textContent = fmtDuration(elapsed);
  }, 250);
}

function appendLog(line) {
  const el = $("log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

function resetLog() {
  $("log").textContent = "";
}

async function refreshStatsAndRuns() {
  const stats = await fetch("/api/stats").then((r) => r.json());
  $("runsTotal").textContent = stats.runs_total ?? "-";
  $("runsSucceeded").textContent = stats.runs_succeeded ?? "-";
  $("runsFailed").textContent = stats.runs_failed ?? "-";
  $("runsCancelled").textContent = stats.runs_cancelled ?? "-";
  $("avgDuration").textContent = stats.avg_duration_s ? fmtDuration(stats.avg_duration_s) : "-";
  $("avgTokens").textContent = stats.avg_total_tokens ? Math.round(stats.avg_total_tokens) : "-";
  if (stats.duration_trend_last10_vs_prev10 === null || stats.duration_trend_last10_vs_prev10 === undefined) {
    $("trend").textContent = "-";
  } else {
    const pct = (stats.duration_trend_last10_vs_prev10 * 100).toFixed(1);
    $("trend").textContent = `${pct}%`;
  }

  const runsResp = await fetch("/api/runs").then((r) => r.json());
  const tbody = $("runsTable");
  tbody.innerHTML = "";
  for (const run of runsResp.runs || []) {
    const tr = document.createElement("tr");
    const started = run.started_at ? new Date(run.started_at).toLocaleString() : "-";
    const dur = run.duration_s ? fmtDuration(run.duration_s) : "-";
    const tokens = run.total_tokens ?? "-";
    tr.innerHTML = `
      <td>${started}</td>
      <td>${run.status}</td>
      <td>${dur}</td>
      <td>${run.tool_calls ?? 0}</td>
      <td>${tokens}</td>
      <td>${(run.goal || "").slice(0, 120)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function connectEvents(runId) {
  if (es) es.close();
  es = new EventSource(`/api/runs/${runId}/events`);
  es.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data);
      if (payload.kind === "eof") {
        es.close();
        es = null;
        $("status").textContent = "idle";
        $("stop").disabled = true;
        $("start").disabled = false;
        setTimerRunning(false);
        refreshStatsAndRuns();
        return;
      }
      if (payload.kind === "assistant") {
        appendLog(`assistant: ${payload.content}`);
      } else if (payload.kind === "tool") {
        appendLog(`tool: ${JSON.stringify(payload.content)}`);
      } else if (payload.kind === "final") {
        appendLog(`final: ${payload.content}`);
      } else if (payload.kind === "error") {
        appendLog(`error: ${payload.content}`);
      } else if (payload.kind === "status") {
        appendLog(`status: ${JSON.stringify(payload.content)}`);
      } else {
        appendLog(`event: ${evt.data}`);
      }
    } catch {
      appendLog(evt.data);
    }
  };
  es.onerror = () => {
    // We'll let refresh handle final state; SSE can error during reloads.
  };
}

async function startRun() {
  const goal = $("goal").value.trim();
  if (!goal) return;
  $("start").disabled = true;
  $("stop").disabled = false;
  $("status").textContent = "running";
  resetLog();
  setTimerRunning(true);

  const workspace = $("workspace").textContent;
  const resp = await fetch("/api/runs/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ goal, workspace }),
  }).then((r) => r.json());

  currentRunId = resp.run_id;
  $("runId").textContent = currentRunId || "-";
  if (currentRunId) connectEvents(currentRunId);
  refreshStatsAndRuns();
}

async function stopRun() {
  if (!currentRunId) return;
  $("stop").disabled = true;
  await fetch(`/api/runs/${currentRunId}/stop`, { method: "POST" });
  appendLog("stop requested...");
}

window.addEventListener("DOMContentLoaded", () => {
  $("start").addEventListener("click", startRun);
  $("stop").addEventListener("click", stopRun);
  refreshStatsAndRuns();
  setInterval(refreshStatsAndRuns, 5000);
});

