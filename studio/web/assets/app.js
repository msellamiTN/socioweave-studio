const $ = (id) => document.getElementById(id);
let strategyRows = [];

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
  $("strategy").innerHTML = strategyRows.map(row =>
    `<option value="${row.id}">${row.id} — ${row.name}</option>`
  ).join("");
  renderStrategyHint();
  $("datasets").innerHTML = datasets.datasets.map(row =>
    `<label class="dataset-option"><input type="checkbox" value="${row.id}" checked><span><b>${row.id}</b><small>${row.expected_prompts} prompts</small></span></label>`
  ).join("");
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
