const state = {
  manifest: null,
  decks: [],
  predictions: null,
  models: new Map(),
  sortedModels: [],
  selectedModels: new Set(["voting_top3_BC_DF", "df_gradient_boosting", "bc_gradient_boosting"]),
  scenario: "interesting",
  activeDeckId: null,
  visibleDecks: [],
};

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
  state.sortedModels = [...predictions.models].sort((a, b) => modelScore(b) - modelScore(a));
  bindEvents();
  chooseScenario("interesting");
}

function bindEvents() {
  document.querySelectorAll("[data-scenario]").forEach((button) => {
    button.addEventListener("click", () => chooseScenario(button.dataset.scenario));
  });
  document.querySelectorAll("[data-model-preset]").forEach((button) => {
    button.addEventListener("click", () => applyModelPreset(button.dataset.modelPreset));
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
  renderStory();
  renderModelSelector();
  renderDecks();
  renderDeckDetail();
  renderModels();
}

function renderMeta() {
  const dataset = state.manifest.dataset;
  $("datasetMeta").innerHTML = `
    <strong>${dataset.n_decks.toLocaleString("pt-BR")}</strong> decks<br>
    y1=y2 em <strong>${pct(dataset.exact_y1_y2_agreement)}</strong><br>
    |delta| medio <strong>${num(dataset.mean_abs_y1_y2_delta, 3)}</strong>
  `;
}

function renderStory() {
  const deck = activeDeck();
  $("storyRail").innerHTML = `
    <div class="story-step">
      <span>1</span>
      <strong>Deck real</strong>
      <p>Escolhemos uma lista publicada no Archidekt e extraimos sinais como cores, preco, tutores, combos e game changers.</p>
    </div>
    <div class="story-step">
      <span>2</span>
      <strong>Dois rotulos</strong>
      <p><b>y1</b> e a classificacao da comunidade. <b>y2</b> e a leitura automatizada da calculadora.</p>
    </div>
    <div class="story-step">
      <span>3</span>
      <strong>Modelos</strong>
      <p>Os modelos aprendem apenas y1. y2 aparece aqui so como comparacao interpretativa.</p>
    </div>
    <div class="story-step">
      <span>4</span>
      <strong>Leitura</strong>
      <p>${deck ? esc(caseSummary(deck)) : "Escolha um deck para ver a interpretacao do caso."}</p>
    </div>
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
      <span class="muted">${esc((deck.commanders || []).join(" / ") || "Comandante nao identificado")}</span>
      <span class="mini-scale">${bracketDots(deck.y1, deck.y2)}</span>
      <span class="muted">y1 ${deck.y1} / y2 ${deck.y2} / ${deck.view_count.toLocaleString("pt-BR")} views</span>
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
  if (deck.delta === 0) return "As duas fontes concordam neste deck. Ele e bom para mostrar quando o problema parece menos ambiguo.";
  if (deck.delta > 0) return "A calculadora colocou este deck acima da comunidade. Isso sugere sinais objetivos de forca que a comunidade classificou com mais cautela.";
  return "A calculadora colocou este deck abaixo da comunidade. Isso sugere que a comunidade atribuiu mais forca ao deck do que a regra automatizada capturou.";
}

function caseSummary(deck) {
  if (deck.delta === 0) return `Caso de consenso: comunidade e calculadora colocam o deck no bracket ${deck.y1}.`;
  if (deck.delta > 0) return `Caso de divergencia: a calculadora sobe de ${deck.y1} para ${deck.y2}.`;
  return `Caso de divergencia: a calculadora desce de ${deck.y1} para ${deck.y2}.`;
}

function deltaLabel(deck) {
  if (deck.delta === 0) return "0";
  return deck.delta > 0 ? `+${deck.delta}` : String(deck.delta);
}

function deltaPill(deck) {
  if (deck.delta === 0) return `<span class="pill good">concordam</span>`;
  if (deck.delta > 0) return `<span class="pill warn">calculadora acima</span>`;
  return `<span class="pill bad">calculadora abaixo</span>`;
}

function primaryCommander(deck) {
  return (deck.commanders || [])[0] || "";
}

function commanderImageUrl(deck) {
  const commander = primaryCommander(deck);
  if (!commander) return "";
  return `https://api.scryfall.com/cards/named?format=image&version=normal&exact=${encodeURIComponent(commander)}`;
}

function bracketDots(y1, y2) {
  return LABELS.map((label) => {
    const markers = [
      y1 === label ? `<span class="marker y1">y1</span>` : "",
      y2 === label ? `<span class="marker y2">y2</span>` : "",
    ].join("");
    return `<span class="dot ${y1 === label || y2 === label ? "filled" : ""}"><b>${label}</b>${markers}</span>`;
  }).join("");
}

function renderDeckDetail() {
  const deck = activeDeck();
  if (!deck) {
    $("deckDetail").innerHTML = `<p class="muted">Nenhum deck encontrado neste cenario.</p>`;
    $("deckLink").href = "#";
    $("caseReading").innerHTML = "";
    return;
  }
  $("deckLink").href = deck.archidekt_url;
  const features = [
    ["Game changers", deck.features.game_changer_count],
    ["Tutores", deck.features.tutor_count],
    ["Combos unicos", deck.features.unique_atomic_combo_refs_count],
    ["Salt medio", deck.features.salt_mean == null ? "n/d" : Number(deck.features.salt_mean).toFixed(3)],
    ["CMC medio", deck.features.nonland_cmc_mean == null ? "n/d" : Number(deck.features.nonland_cmc_mean).toFixed(2)],
    ["Terrenos", deck.features.land_count],
    ["Cores", deck.colors || "C"],
  ];
  $("deckDetail").innerHTML = `
    <div class="deck-hero">
      <div class="deck-showcase">
        <figure class="commander-frame">
          ${commanderImageUrl(deck)
            ? `<img src="${commanderImageUrl(deck)}" alt="${esc(primaryCommander(deck))}" loading="lazy" onerror="this.closest('.commander-frame').classList.add('missing'); this.remove();">`
            : ""}
          <figcaption>${esc(primaryCommander(deck) || "Comandante nao identificado")}</figcaption>
        </figure>
        <div class="deck-main">
          <h3>${esc(deck.name)}</h3>
          <p class="muted">${esc((deck.commanders || []).join(" / ") || "Comandante nao identificado")}</p>
          <div class="bracket-scale">${bracketDots(deck.y1, deck.y2)}</div>
          <div class="pill-row">
            <span class="pill">y1 comunidade: ${deck.y1}</span>
            <span class="pill">y2 calculadora: ${deck.y2}</span>
            ${deltaPill(deck)}
          </div>
          <p>${deltaText(deck)}</p>
        </div>
      </div>
      <div class="calculator-board">
        <div class="stat-tile big"><span>y1 comunidade</span><strong>Bracket ${deck.y1}</strong></div>
        <div class="stat-tile"><span>y2 calculadora</span><strong>Bracket ${deck.y2}</strong></div>
        <div class="stat-tile"><span>Diferenca</span><strong>${deltaLabel(deck)}</strong></div>
        <div class="stat-tile"><span>Views</span><strong>${deck.view_count.toLocaleString("pt-BR")}</strong></div>
      </div>
      <div class="signal-bars">${signalBars(deck)}</div>
      <div class="feature-grid">
        ${features.map(([label, value]) => `<div class="feature"><span>${label}</span><strong>${value ?? "n/d"}</strong></div>`).join("")}
      </div>
    </div>
  `;
  renderCaseReading(deck);
}

function signalBars(deck) {
  const signals = [
    ["Game changers", Number(deck.features.game_changer_count || 0), 10],
    ["Tutores", Number(deck.features.tutor_count || 0), 12],
    ["Combos", Number(deck.features.unique_atomic_combo_refs_count || 0), 12],
    ["Salt medio", Number(deck.features.salt_mean || 0), 1],
    ["CMC medio", Number(deck.features.nonland_cmc_mean || 0), 6],
    ["Terrenos", Number(deck.features.land_count || 0), 45],
  ];
  return signals.map(([label, value, max]) => `
    <div class="signal-row">
      <span>${label}</span>
      <div class="signal-track"><i style="width:${Math.min(100, 100 * value / max).toFixed(1)}%"></i></div>
      <b>${formatSignalValue(label, deck, value)}</b>
    </div>
  `).join("");
}

function formatSignalValue(label, deck, value) {
  if (label === "Salt medio") return deck.features.salt_mean == null ? "n/d" : Number(deck.features.salt_mean).toFixed(3);
  if (label === "CMC medio") return deck.features.nonland_cmc_mean == null ? "n/d" : Number(deck.features.nonland_cmc_mean).toFixed(2);
  return value;
}

function deckIndex(deck) {
  return state.predictions.deck_order.indexOf(deck.snapshot_id);
}

function modelScore(model) {
  return model.global_metrics.macro_f1_mean ?? model.global_metrics.deck_level_macro_f1_y1 ?? 0;
}

function modelPrediction(model, deck) {
  const idx = deckIndex(deck);
  return {
    pred: model.predictions[idx],
    confidence: model.confidence[idx] || 0,
    counts: model.counts?.[idx] || [0, 0, 0],
  };
}

function predictionMeaning(pred, deck) {
  if (pred === deck.y1 && pred === deck.y2) return "bate com as duas fontes.";
  if (pred === deck.y1) return "ficou mais perto da comunidade.";
  if (pred === deck.y2) return "ficou mais perto da calculadora.";
  return "discorda das duas fontes.";
}

function selectedModelsSorted() {
  return state.sortedModels.filter((model) => state.selectedModels.has(model.id));
}

function renderModelSelector() {
  $("modelCount").textContent = `${state.selectedModels.size} selecionado${state.selectedModels.size === 1 ? "" : "s"}`;
  $("modelSelector").innerHTML = state.sortedModels.map((model, index) => {
    const checked = state.selectedModels.has(model.id);
    const kind = model.type === "ensemble" ? "ensemble" : model.id.startsWith("df_") ? "DF" : "BC";
    return `
      <button class="model-option ${checked ? "active" : ""}" data-model-toggle="${esc(model.id)}">
        <span class="rank">${index + 1}</span>
        <span>
          <strong>${esc(model.label)}</strong>
          <small>${kind} / macro-F1 ${num(modelScore(model), 3)}</small>
        </span>
      </button>
    `;
  }).join("");
  document.querySelectorAll("[data-model-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.modelToggle;
      if (state.selectedModels.has(id)) state.selectedModels.delete(id);
      else state.selectedModels.add(id);
      if (!state.selectedModels.size) state.selectedModels.add(id);
      render();
    });
  });
}

function applyModelPreset(preset) {
  const models = state.sortedModels;
  if (preset === "top3") state.selectedModels = new Set(models.slice(0, 3).map((model) => model.id));
  if (preset === "df") state.selectedModels = new Set(models.filter((model) => model.id.startsWith("df_")).map((model) => model.id));
  if (preset === "bc") state.selectedModels = new Set(models.filter((model) => model.id.startsWith("bc_")).map((model) => model.id));
  if (preset === "ensemble") state.selectedModels = new Set(models.filter((model) => model.type === "ensemble").map((model) => model.id));
  if (preset === "all") state.selectedModels = new Set(models.map((model) => model.id));
  render();
}

function renderModels() {
  const deck = activeDeck();
  if (!deck) {
    $("modelCards").innerHTML = `<p class="muted">Escolha um deck.</p>`;
    return;
  }
  $("modelCards").innerHTML = selectedModelsSorted().map((model) => {
    const result = modelPrediction(model, deck);
    const cls = result.pred === deck.y1 ? "good" : result.pred === deck.y2 ? "warn" : "bad";
    return `
      <article class="model-result">
        <div class="model-head">
          <h3>${esc(model.label)}</h3>
          <span>${model.type === "ensemble" ? "ensemble" : "modelo individual"} / macro-F1 ${num(modelScore(model), 3)}</span>
        </div>
        <div class="model-prediction">
          <span>predicao</span>
          <strong>${result.pred}</strong>
          <span class="pill ${cls}">${pct(result.confidence)} dos repeats</span>
        </div>
        <div class="repeat-bars">${repeatBars(result.counts)}</div>
        <p class="explain">Neste deck, este modelo ${predictionMeaning(result.pred, deck)}</p>
      </article>
    `;
  }).join("");
}

function repeatBars(counts) {
  const total = counts.reduce((sum, value) => sum + value, 0) || 1;
  return LABELS.map((label, index) => {
    const count = counts[index] || 0;
    return `
      <div class="repeat-row">
        <span>${label}</span>
        <div class="repeat-track"><i style="width:${(100 * count / total).toFixed(1)}%"></i></div>
        <b>${count}/${total}</b>
      </div>
    `;
  }).join("");
}

function renderCaseReading(deck) {
  const selected = selectedModelsSorted();
  const predictions = selected.map((model) => modelPrediction(model, deck).pred);
  const y1Hits = predictions.filter((pred) => pred === deck.y1).length;
  const y2Hits = predictions.filter((pred) => pred === deck.y2).length;
  const otherHits = predictions.filter((pred) => pred !== deck.y1 && pred !== deck.y2).length;
  const leaning = y1Hits > y2Hits ? "mais perto da comunidade" : y2Hits > y1Hits ? "mais perto da calculadora" : "sem vencedor claro";
  $("caseReading").innerHTML = `
    <h2>Leitura do caso</h2>
    <p><strong>${caseSummary(deck)}</strong> Os modelos selecionados ficam ${leaning}: ${y1Hits} batem com y1, ${y2Hits} batem com y2${otherHits ? `, e ${otherHits} vao para outro bracket` : ""}.</p>
    <p class="muted">Como y2 nao entra no treino, quando um modelo se aproxima de y2 isso e uma evidencia descritiva, nao uma meta otimizada pelo experimento.</p>
  `;
}

start().catch((error) => {
  document.body.innerHTML = `<main class="panel" style="margin: 20px"><h1>Demo nao carregou</h1><p>${esc(error.message)}</p><p>Rode <code>uv run --no-sync python -m scripts.demo build</code>.</p></main>`;
});
