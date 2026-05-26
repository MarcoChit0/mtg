const state = {
  manifest: null,
  decks: [],
  predictions: null,
  models: new Map(),
  scenario: "interesting",
  activeDeckId: null,
  visibleDecks: [],
};

const MAIN_MODELS = ["df_gradient_boosting", "bc_gradient_boosting", "voting_top3_BC_DF"];
const LABELS = [2, 3, 4];
const $ = (id) => document.getElementById(id);

function pct(value) {
  return `${(100 * (value || 0)).toFixed(1)}%`;
}

function num(value, digits = 3) {
  return Number(value || 0).toFixed(digits);
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function start() {
  const [manifest, decks, predictions] = await Promise.all([
    loadJson("assets/manifest.json"),
    loadJson("assets/decks.json"),
    loadJson("assets/predictions.json"),
  ]);
  state.manifest = manifest;
  state.decks = decks;
  state.predictions = predictions;
  state.models = new Map(predictions.models.map((model) => [model.id, model]));
  bindEvents();
  chooseScenario("interesting");
}

function bindEvents() {
  document.querySelectorAll("[data-scenario]").forEach((button) => {
    button.addEventListener("click", () => chooseScenario(button.dataset.scenario));
  });
  $("deckSearch").addEventListener("input", renderDecks);
}

function chooseScenario(scenario) {
  state.scenario = scenario;
  document.querySelectorAll("[data-scenario]").forEach((button) => {
    button.classList.toggle("active", button.dataset.scenario === scenario);
  });
  const decks = scenarioDecks();
  state.activeDeckId = decks[0]?.snapshot_id || null;
  render();
}

function scenarioDecks() {
  const sorted = [...state.decks].sort((a, b) => b.view_count - a.view_count);
  if (state.scenario === "agree") return sorted.filter((deck) => deck.delta === 0).slice(0, 12);
  if (state.scenario === "calc_above") return sorted.filter((deck) => deck.delta > 0).slice(0, 12);
  if (state.scenario === "calc_below") return sorted.filter((deck) => deck.delta < 0).slice(0, 12);

  const agree = sorted.find((deck) => deck.delta === 0);
  const above = sorted.find((deck) => deck.delta > 0);
  const below = sorted.find((deck) => deck.delta < 0);
  const large = sorted.find((deck) => Math.abs(deck.delta) === 2);
  const highGc = sorted.find((deck) => Number(deck.features.game_changer_count || 0) >= 5);
  const picked = [agree, above, below, large, highGc].filter(Boolean);
  const seen = new Set(picked.map((deck) => deck.snapshot_id));
  for (const deck of sorted) {
    if (picked.length >= 12) break;
    if (!seen.has(deck.snapshot_id)) {
      picked.push(deck);
      seen.add(deck.snapshot_id);
    }
  }
  return picked;
}

function render() {
  renderMeta();
  renderDecks();
  renderDeckDetail();
  renderModels();
  renderMetrics();
}

function renderMeta() {
  const dataset = state.manifest.dataset;
  $("datasetMeta").innerHTML = `
    <strong>${dataset.n_decks.toLocaleString("pt-BR")}</strong> decks<br>
    y1=y2 em <strong>${pct(dataset.exact_y1_y2_agreement)}</strong><br>
    |delta| médio <strong>${num(dataset.mean_abs_y1_y2_delta, 3)}</strong>
  `;
}

function filteredScenarioDecks() {
  const query = $("deckSearch").value.trim().toLowerCase();
  const decks = scenarioDecks();
  if (!query) return decks;
  return decks.filter((deck) => {
    const text = `${deck.name} ${deck.deck_id} ${(deck.commanders || []).join(" ")}`.toLowerCase();
    return text.includes(query);
  });
}

function renderDecks() {
  state.visibleDecks = filteredScenarioDecks();
  if (!state.visibleDecks.some((deck) => deck.snapshot_id === state.activeDeckId)) {
    state.activeDeckId = state.visibleDecks[0]?.snapshot_id || null;
  }
  $("deckList").innerHTML = state.visibleDecks.map((deck) => `
    <button class="deck-button ${deck.snapshot_id === state.activeDeckId ? "active" : ""}" data-deck="${esc(deck.snapshot_id)}">
      <span class="deck-title">${esc(deck.name)}</span>
      <span class="muted">${esc((deck.commanders || []).join(" / ") || "Comandante não identificado")}</span>
      <span class="muted">y1 ${deck.y1} · y2 ${deck.y2} · ${deck.view_count.toLocaleString("pt-BR")} views</span>
    </button>
  `).join("");
  document.querySelectorAll("[data-deck]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeDeckId = button.dataset.deck;
      render();
    });
  });
}

function activeDeck() {
  return state.decks.find((deck) => deck.snapshot_id === state.activeDeckId);
}

function deltaText(deck) {
  if (!deck) return "";
  if (deck.delta === 0) return "As duas fontes concordam neste deck.";
  if (deck.delta > 0) return "A calculadora colocou este deck acima da comunidade.";
  return "A calculadora colocou este deck abaixo da comunidade.";
}

function deltaPill(deck) {
  if (deck.delta === 0) return `<span class="pill good">concordam</span>`;
  if (deck.delta > 0) return `<span class="pill warn">calculadora acima</span>`;
  return `<span class="pill bad">calculadora abaixo</span>`;
}

function renderDeckDetail() {
  const deck = activeDeck();
  if (!deck) {
    $("deckDetail").innerHTML = `<p class="muted">Nenhum deck encontrado neste cenário.</p>`;
    $("deckLink").href = "#";
    return;
  }
  $("deckLink").href = deck.archidekt_url;
  const features = [
    ["Game changers", deck.features.game_changer_count],
    ["Tutores", deck.features.tutor_count],
    ["Combos únicos", deck.features.unique_atomic_combo_refs_count],
    ["Preço", deck.features.price_total == null ? "n/d" : `$${Number(deck.features.price_total).toLocaleString("en-US")}`],
    ["Power level", deck.power_level ?? "n/d"],
    ["Cores", deck.colors || "C"],
  ];
  $("deckDetail").innerHTML = `
    <div class="deck-hero">
      <h3>${esc(deck.name)}</h3>
      <p class="muted">${esc((deck.commanders || []).join(" / ") || "Comandante não identificado")}</p>
      <div class="pill-row">
        <span class="pill">y1 Archidekt: ${deck.y1}</span>
        <span class="pill">y2 Calculadora: ${deck.y2}</span>
        ${deltaPill(deck)}
      </div>
      <p>${deltaText(deck)}</p>
      <div class="feature-grid">
        ${features.map(([label, value]) => `<div class="feature"><span>${label}</span><strong>${value ?? "n/d"}</strong></div>`).join("")}
      </div>
    </div>
  `;
}

function deckIndex(deck) {
  return state.predictions.deck_order.indexOf(deck.snapshot_id);
}

function modelPrediction(model, deck) {
  const idx = deckIndex(deck);
  return {
    pred: model.predictions[idx],
    confidence: model.confidence[idx] || 0,
  };
}

function predictionMeaning(pred, deck) {
  if (pred === deck.y1 && pred === deck.y2) return "bate com as duas fontes.";
  if (pred === deck.y1) return "ficou mais perto da comunidade.";
  if (pred === deck.y2) return "ficou mais perto da calculadora.";
  return "discorda das duas fontes.";
}

function renderModels() {
  const deck = activeDeck();
  if (!deck) {
    $("modelCards").innerHTML = `<p class="muted">Escolha um deck.</p>`;
    return;
  }
  $("modelCards").innerHTML = MAIN_MODELS.map((id) => {
    const model = state.models.get(id);
    const result = modelPrediction(model, deck);
    const cls = result.pred === deck.y1 ? "good" : result.pred === deck.y2 ? "warn" : "bad";
    const macro = model.global_metrics.macro_f1_mean ?? model.global_metrics.deck_level_macro_f1_y1;
    return `
      <article class="model-result">
        <h3>${esc(model.label)}</h3>
        <span>${model.type === "ensemble" ? "ensemble" : "modelo individual"} · macro-F1 global ${num(macro, 3)}</span>
        <div class="model-prediction">
          <span>predição</span>
          <strong>${result.pred}</strong>
          <span class="pill ${cls}">${pct(result.confidence)} dos repeats</span>
        </div>
        <p class="explain">Neste deck, este modelo ${predictionMeaning(result.pred, deck)}</p>
      </article>
    `;
  }).join("");
}

function confusionFor(model, decks) {
  const matrix = LABELS.map(() => LABELS.map(() => 0));
  for (const deck of decks) {
    const pred = modelPrediction(model, deck).pred;
    const row = LABELS.indexOf(deck.y1);
    const col = LABELS.indexOf(pred);
    if (row >= 0 && col >= 0) matrix[row][col] += 1;
  }
  const total = matrix.flat().reduce((sum, value) => sum + value, 0);
  const correct = LABELS.reduce((sum, _, idx) => sum + matrix[idx][idx], 0);
  return { total, accuracy: total ? correct / total : 0 };
}

function renderMetrics() {
  const decks = state.visibleDecks;
  const agreement = decks.length ? decks.filter((deck) => deck.y1 === deck.y2).length / decks.length : 0;
  const meanAbs = decks.length ? decks.reduce((sum, deck) => sum + Math.abs(deck.delta), 0) / decks.length : 0;
  const bestDf = confusionFor(state.models.get("df_gradient_boosting"), decks);
  const ensemble = confusionFor(state.models.get("voting_top3_BC_DF"), decks);
  $("scenarioMetrics").innerHTML = `
    <div class="metric"><span>Decks mostrados</span><strong>${decks.length}</strong></div>
    <div class="metric"><span>Concordância y1=y2</span><strong>${pct(agreement)}</strong></div>
    <div class="metric"><span>|delta| médio</span><strong>${num(meanAbs, 2)}</strong></div>
    <div class="metric"><span>Acc. melhor DF</span><strong>${pct(bestDf.accuracy)}</strong></div>
    <div class="metric"><span>Acc. ensemble</span><strong>${pct(ensemble.accuracy)}</strong></div>
  `;
}

start().catch((error) => {
  document.body.innerHTML = `<main class="panel" style="margin: 20px"><h1>Demo não carregou</h1><p>${esc(error.message)}</p><p>Rode <code>uv run --no-sync python -m scripts.demo build</code>.</p></main>`;
});
