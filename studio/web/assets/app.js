const $ = (id) => document.getElementById(id);
let strategyRows = [];
let datasetRows = [];
let lastPreflightReport = null;
let lastCampaignPreflightReport = null;

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
  const [strategies, datasets, jigsawPolicy, capabilities] = await Promise.all([
    api("/api/v1/strategies"),
    api("/api/v1/datasets"),
    api("/api/v1/jigsaw/policy"),
    api("/api/v1/capabilities"),
  ]);
  renderOverview(strategies, datasets, capabilities);
  renderDatasetRegistry(datasets);
  strategyRows = strategies.strategies;
  datasetRows = datasets.datasets;
  $("s12-factory-id").value = jigsawPolicy.factory_id;
  $("s12-factory-sha").value = jigsawPolicy.policy_sha256;
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
  $("preflight-state").className = "pill warning";
  $("frozen-datasets").textContent = Object.keys(report.dataset_prompt_counts).length;
  $("preflight-conditions").textContent = report.condition_count.toLocaleString();
  $("preflight-strategies").textContent = report.strategy_count;
  $("snapshot-hash").textContent = report.snapshot_sha256;
  $("dataset-counts").innerHTML = Object.entries(report.dataset_prompt_counts)
    .map(([name, count]) => `<li><b>${name}</b> — ${count} frozen prompts</li>`).join("");
  $("preflight-blockers").innerHTML = report.blocking_requirements.map(item => `<li>${item}</li>`).join("");
  $("preflight-caveat").textContent = "This dataset/grid preflight does not validate provider rosters, model-family provenance, fixed executor identity, S12 prompt-view configuration, annotation quality, model connectivity or cost ceilings. It does not authorize or launch experiments.";
  $("preflight-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("verify-snapshot-manifest").addEventListener("click", async () => {
  const button = $("verify-snapshot-manifest");
  const resultBox = $("snapshot-verify-result");
  button.disabled = true;
  resultBox.classList.add("hidden");
  $("snapshot-verify-status").textContent = "Checking manifest structure and digest…";
  try {
    const parsed = JSON.parse($("snapshot-manifest-input").value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Snapshot manifest must be a JSON object.");
    }
    const report = await api("/api/v1/snapshots/verify", {
      method: "POST",
      body: JSON.stringify({ snapshot_manifest: parsed }),
    });
    $("snapshot-verify-title").textContent = report.verification;
    $("snapshot-verify-detail").textContent =
      `${report.dataset_count} datasets · ${report.total_prompt_count} prompts · ${report.evidence_state}. Source files rechecked: no. E1_READY: false.`;
    $("snapshot-verify-hash").textContent = report.snapshot_sha256;
    resultBox.classList.remove("hidden");
    $("snapshot-verify-status").textContent = "Manifest integrity check passed; scientific and source claims remain unverified.";
  } catch (error) {
    $("snapshot-verify-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

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
    $("preflight-status").textContent = "Dataset/grid validation passed · full campaign preflight still pending";
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



function showCampaignPreflight(report) {
  lastCampaignPreflightReport = report;
  $("campaign-preflight-results").classList.remove("hidden");
  $("campaign-preflight-title").textContent = "Engine-backed E1 campaign configuration validation";
  $("campaign-preflight-summary").textContent = report.note;
  $("campaign-preflight-state").textContent = report.readiness;
  $("campaign-preflight-state").className = "pill warning";
  $("campaign-condition-count").textContent = report.condition_count.toLocaleString();
  $("campaign-roster-count").textContent = report.provider_rosters_validated;
  $("campaign-model-modes").textContent = report.model_modes.join(" + ");
  $("campaign-provider-hash").textContent = report.engine_report.provider_manifest_sha256;
  $("campaign-runtime-hash").textContent = report.runtime_campaign_manifest_sha256;
  $("campaign-remaining-gates").innerHTML = report.remaining_evidence_gates
    .map(item => `<li>${item}</li>`).join("");
  $("campaign-preflight-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("run-campaign-preflight").addEventListener("click", async () => {
  const button = $("run-campaign-preflight");
  button.disabled = true;
  $("campaign-preflight-status").textContent = "Running engine campaign preflight — zero provider calls…";
  $("campaign-preflight-results").classList.add("hidden");
  try {
    const manifestText = $("provider-manifest-json").value.trim();
    if (!manifestText) throw new Error("Paste the canonical non-secret provider campaign manifest first.");
    const provider_manifest = JSON.parse(manifestText);
    if (!provider_manifest || typeof provider_manifest !== "object" || Array.isArray(provider_manifest)) {
      throw new Error("Provider manifest must be a JSON object.");
    }
    const s12_prompt_view_factory_id = $("s12-factory-id").value.trim();
    const s12_prompt_view_factory_sha256 = $("s12-factory-sha").value.trim();
    const report = await api("/api/v1/preflights/e1/campaign", {
      method: "POST",
      body: JSON.stringify({
        sources: readSourceDeclarations(),
        provider_manifest,
        s12_prompt_view_factory_id,
        s12_prompt_view_factory_sha256,
        n: Number($("n").value),
        k: Number($("k").value),
        T: Number($("rounds").value),
      }),
    });
    showCampaignPreflight(report);
    $("campaign-preflight-status").textContent = "Engine configuration preflight passed · no live calls · E1_READY false";
  } catch (error) {
    $("campaign-preflight-status").textContent = error.message;
    $("campaign-preflight-status").style.color = "#e8bd72";
  } finally {
    button.disabled = false;
  }
});

$("export-campaign-preflight").addEventListener("click", () => {
  if (!lastCampaignPreflightReport) return;
  const payload = {
    schema_version: "socioweave-studio-e1-campaign-preflight-export-v1",
    exported_at: new Date().toISOString(),
    report: lastCampaignPreflightReport,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `socioweave-e1-campaign-preflight-${lastCampaignPreflightReport.engine_report.provider_manifest_sha256.slice(0, 12)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
});

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

function renderDatasetRegistry(payload) {
  const boundary = payload.evidence_boundary || "Dataset evidence persistence is not reported by this API.";
  $("dataset-registry-summary").textContent =
    `Registry mode: ${payload.registry_mode || "unspecified"} · Evidence persistence: ${payload.evidence_persistence ? "enabled" : "not enabled"}. ${boundary}`;
  $("dataset-registry-list").innerHTML = payload.datasets.map(row => {
    const meta = row.metadata || {};
    const contract = row.evidence_contract || {};
    const metrics = (meta.metrics || []).map(item => `<li>${escapeHTML(item)}</li>`).join("");
    const source = meta.paper_source_url
      ? `<a href="${escapeHTML(meta.paper_source_url)}" target="_blank" rel="noopener noreferrer">Paper/source reference ↗</a>`
      : "<span class='subtle'>No public source URL registered</span>";
    const reference = meta.reference_provided || "Reference requirement not specified in catalogue";
    return `
      <article class="registry-card">
        <div class="registry-card-head"><div><span class="eyebrow">ENGINE DATASET</span><h4>${escapeHTML(row.id)}</h4></div><span class="pill warning">${escapeHTML(contract.evidence_state || "UNKNOWN")}</span></div>
        <div class="registry-count"><b>${escapeHTML(row.expected_prompts)}</b><span>paper prompts expected</span></div>
        <p class="registry-description">${escapeHTML(meta.prompt_case || "No prompt case description registered")}</p>
        <dl class="registry-facts">
          <div><dt>Reference structure</dt><dd>${escapeHTML(reference)}</dd></div>
          <div><dt>Source release status</dt><dd>${escapeHTML(meta.source_release_status || "Not specified")}</dd></div>
          <div><dt>Selection requirement</dt><dd>${escapeHTML(meta.selection_protocol || "Explicit selection protocol required")}</dd></div>
          <div><dt>License review</dt><dd>${contract.license_review_required ? "Required · operator evidence not persisted" : "Not marked required in catalogue"}</dd></div>
          <div><dt>Coverage applicability</dt><dd>${escapeHTML(meta.coverage_applicable === false ? "Not applicable" : meta.coverage_applicable || "Not specified")}</dd></div>
        </dl>
        <div class="registry-metrics"><b>Registered metric scope</b><ul>${metrics}</ul></div>
        <div class="registry-source">${source}</div>
        <p class="registry-footnote">Catalogue contract only. No source revision, selected IDs, approval or annotation evidence is stored in this Studio view.</p>
      </article>`;
  }).join("");
}

function renderOverview(strategies, datasets, capabilities) {
  $("overview-datasets").textContent = datasets.datasets.length;
  $("overview-strategies").textContent = strategies.strategies.length;
  $("overview-run-launch").textContent = capabilities.run_launch ? "Enabled" : "Disabled";
  $("overview-live-calls").textContent = capabilities.live_provider_calls_enabled ? "Enabled" : "0";
  $("evidence-state").textContent = capabilities.evidence_state || "UNKNOWN";
  $("evidence-state").className = "pill warning";
  const mode = capabilities.run_launch ? "Execution enabled" : "Configuration-only mode";
  document.querySelector(".sidebar-bottom b").textContent = mode;
  document.querySelector(".sidebar-bottom small").textContent =
    capabilities.live_provider_calls_enabled ? "Provider calls may be enabled" : "Provider execution disabled";
}

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


async function loadEvidenceStatus() {
  const status = await api("/api/v1/evidence/status");
  $("evidence-write-state").textContent = status.write_enabled ? "Writes token-configured" : "Writes disabled by default";
  $("evidence-write-state").className = "pill warning";
}

$("verify-evidence-ledger").addEventListener("click", async () => {
  const button = $("verify-evidence-ledger");
  button.disabled = true;
  $("evidence-ledger-status").textContent = "Verifying append-only hash chain…";
  try {
    const result = await api("/api/v1/evidence/ledger/verify");
    $("ledger-event-count").textContent = result.event_count.toLocaleString();
    $("ledger-chain-state").textContent = result.verification === "LEDGER_CHAIN_VALID" ? "Valid" : "Invalid";
    $("evidence-ledger-status").textContent =
      result.verification + " · head " + result.head_hash.slice(0, 16) + "… · " + result.errors.length + " integrity errors";
  } catch (error) {
    $("evidence-ledger-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("verify-evidence-blob").addEventListener("click", async () => {
  const digest = $("evidence-blob-digest").value.trim();
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    $("evidence-blob-status").textContent = "Enter a lowercase 64-character SHA-256 digest.";
    return;
  }
  const button = $("verify-evidence-blob");
  button.disabled = true;
  $("evidence-blob-status").textContent = "Recomputing SHA-256 from archived bytes…";
  try {
    const result = await api("/api/v1/evidence/blobs/" + digest + "/verify");
    $("evidence-blob-status").textContent =
      result.verification + " · source bytes rechecked: " + result.source_file_rechecked;
  } catch (error) {
    $("evidence-blob-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

loadEvidenceStatus().catch(error => {
  $("evidence-write-state").textContent = "Status unavailable: " + error.message;
});
