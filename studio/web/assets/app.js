const $ = (id) => document.getElementById(id);
let strategyRows = [];
let datasetRows = [];
let lastPreflightReport = null;

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(Array.isArray(detail) ? detail.map(x => x.msg).join("; ") : String(detail || response.statusText));
  }
  return body;
}

async function loadCatalogue() {
  const [strategies, datasets] = await Promise.all([
    api("/api/v1/strategies"),
    api("/api/v1/datasets"),
  ]);
  strategyRows = strategies.strategies;
  datasetRows = datasets.datasets;
  $("strategy").innerHTML = strategyRows.map(row =>
    `<option value="${row.id}">${row.id} — ${row.name}</option>`
  ).join("");
  renderStrategyHint();
  renderSourceDeclarations();
  $("datasets").innerHTML = datasets.datasets.map(row =>
    `<label class="dataset-option"><input type="checkbox" value="${row.id}" checked><span><b>${row.id}</b><small>${row.expected_prompts} prompts</small></span></label>`
  ).join("");
}



function renderSourceDeclarations() {
  $("source-declarations").innerHTML = datasetRows.map(row => {
    const id = row.id;
    const safeId = id.replace(/[^a-zA-Z0-9_-]/g, "-");
    const metadata = row.metadata || {};
    const reference = metadata.reference_provided || "Structured reference data required by the registered dataset contract";
    return `
      <fieldset class="source-card" data-dataset="${id}">
        <legend><b>${id}</b><span>${row.expected_prompts} prompts</span></legend>
        <p class="source-reference">${reference}</p>
        <label class="source-field full"><span>Absolute server-local JSONL path</span><input id="path-${safeId}" autocomplete="off" placeholder="/data/benchmarks/${id}.jsonl" required></label>
        <div class="source-fields">
          <label class="source-field"><span>Source version</span><input id="version-${safeId}" placeholder="Exact release / commit / version" required></label>
          <label class="source-field"><span>Selected split</span><input id="split-${safeId}" placeholder="Exact split name" required></label>
          <label class="source-field full"><span>Prompt selection protocol</span><input id="selection-${safeId}" placeholder="Exact selection procedure and prompt IDs" required></label>
          <label class="source-field"><span>License review</span><select id="license-${safeId}"><option value="pending" selected>Pending review</option><option value="approved">Approved by operator</option></select></label>
          <label class="source-field"><span>Selection seed (optional)</span><input id="seed-${safeId}" type="number" min="0" step="1" placeholder="Not declared"></label>
        </div>
      </fieldset>`;
  }).join("");
}

function readSourceDeclarations() {
  return Object.fromEntries(datasetRows.map(row => {
    const safeId = row.id.replace(/[^a-zA-Z0-9_-]/g, "-");
    const path = $(`path-${safeId}`).value.trim();
    const source_version = $(`version-${safeId}`).value.trim();
    const split = $(`split-${safeId}`).value.trim();
    const selection_protocol = $(`selection-${safeId}`).value.trim();
    const license_review_status = $(`license-${safeId}`).value;
    const seedRaw = $(`seed-${safeId}`).value.trim();
    if (!path || !source_version || !split || !selection_protocol) {
      throw new Error(`${row.id}: provide the path, source version, split and exact selection protocol.`);
    }
    if (license_review_status !== "approved") {
      throw new Error(`${row.id}: license review must be explicitly approved before snapshot freezing.`);
    }
    if (seedRaw && (!/^\d+$/.test(seedRaw) || !Number.isSafeInteger(Number(seedRaw)))) {
      throw new Error(`${row.id}: selection seed must be a non-negative integer.`);
    }
    return [row.id, {
      path, source_version, split, selection_protocol,
      license_review_status,
      selection_seed: seedRaw ? Number(seedRaw) : null,
    }];
  }));
}

function showPreflight(report) {
  lastPreflightReport = report;
  $("preflight-results").classList.remove("hidden");
  $("preflight-title").textContent = "E1 snapshot and condition-grid validation";
  $("preflight-summary").textContent = report.note;
  $("preflight-state").textContent = report.readiness;
  $("preflight-state").className = "pill success";
  $("frozen-datasets").textContent = Object.keys(report.dataset_prompt_counts).length;
  $("preflight-conditions").textContent = report.condition_count.toLocaleString();
  $("preflight-strategies").textContent = report.strategy_count;
  $("snapshot-hash").textContent = report.snapshot_sha256;
  $("dataset-counts").innerHTML = Object.entries(report.dataset_prompt_counts)
    .map(([name, count]) => `<li><b>${name}</b> — ${count} frozen prompts</li>`).join("");
  $("preflight-blockers").innerHTML = report.blocking_requirements.map(item => `<li>${item}</li>`).join("");
  $("preflight-caveat").textContent = "A successful configuration preflight does not verify the truth of licensing or provider-family declarations, annotation quality, model connectivity, executor identity or cost ceilings. It does not authorize or launch experiments.";
  $("preflight-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("run-preflight").addEventListener("click", async () => {
  const button = $("run-preflight");
  button.disabled = true;
  $("preflight-status").textContent = "Validating local sources and building the complete E1 grid…";
  $("preflight-results").classList.add("hidden");
  try {
    const sources = readSourceDeclarations();
    const report = await api("/api/v1/preflights/e1", {
      method: "POST",
      body: JSON.stringify({
        sources,
        n: Number($("n").value),
        k: Number($("k").value),
        T: Number($("rounds").value),
      }),
    });
    showPreflight(report);
    $("preflight-status").textContent = "Preflight passed · no model or provider calls made";
  } catch (error) {
    $("preflight-status").textContent = error.message;
    $("preflight-status").style.color = "#e8bd72";
  } finally {
    button.disabled = false;
  }
});

$("copy-hash").addEventListener("click", async () => {
  if (!lastPreflightReport) return;
  try {
    await navigator.clipboard.writeText(lastPreflightReport.snapshot_sha256);
    $("copy-hash").textContent = "Copied";
  } catch {
    $("copy-hash").textContent = "Clipboard unavailable";
  }
});

$("export-preflight").addEventListener("click", () => {
  if (!lastPreflightReport) return;
  const payload = {
    schema_version: "socioweave-studio-e1-preflight-export-v1",
    exported_at: new Date().toISOString(),
    report: lastPreflightReport,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `socioweave-e1-preflight-${lastPreflightReport.snapshot_sha256.slice(0, 12)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
});

function renderStrategyHint() {
  const row = strategyRows.find(item => item.id === $("strategy").value);
  $("strategy-hint").textContent = row
    ? `Paper formula: ${row.call_formula} calls per prompt · Depth: ${row.depth_formula}`
    : "Paper catalogue definition";
}

function parseSeeds() {
  const raw = $("seeds").value.trim();
  if (!raw) throw new Error("Enter at least one seed index.");
  const values = raw.split(",").map(item => {
    if (!/^\d+$/.test(item.trim())) throw new Error("Seed indices must be comma-separated integers.");
    return Number(item.trim());
  });
  if (new Set(values).size !== values.length) throw new Error("Seed indices must not contain duplicates.");
  return values;
}

function showPreview(result) {
  $("results").classList.remove("hidden");
  $("prompt-count").textContent = result.expected_prompt_count.toLocaleString();
  $("condition-count").textContent = result.condition_count.toLocaleString();
  $("method-calls").textContent = result.estimated_method_calls.toLocaleString();
  const row = strategyRows.find(item => item.id === result.strategy_id);
  $("formula").textContent = `${row.call_formula} = ${result.method_calls_per_prompt} calls / prompt`;
  $("strategy-description").textContent = row.protocol_summary;
  $("blockers").innerHTML = result.blocking_requirements.map(item => `<li>${item}</li>`).join("");
  $("preview-note").textContent = result.note;
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("strategy").addEventListener("change", renderStrategyHint);
$("preview").addEventListener("click", async () => {
  const button = $("preview");
  button.disabled = true;
  $("form-status").textContent = "Calculating…";
  try {
    const datasets = [...document.querySelectorAll("#datasets input:checked")].map(item => item.value);
    const result = await api("/api/v1/config-previews", {
      method: "POST",
      body: JSON.stringify({
        strategy_id: $("strategy").value,
        datasets,
        model_mode: $("mode").value,
        n: Number($("n").value),
        k: Number($("k").value),
        T: Number($("rounds").value),
        seed_indices: parseSeeds(),
      }),
    });
    showPreview(result);
    $("form-status").textContent = "Preview calculated · execution remains locked";
  } catch (error) {
    $("form-status").textContent = error.message;
    $("form-status").style.color = "#e8bd72";
  } finally {
    button.disabled = false;
  }
});

loadCatalogue().catch(error => {
  $("form-status").textContent = `Could not load API catalogue: ${error.message}`;
});
