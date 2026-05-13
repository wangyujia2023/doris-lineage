const state = {
  tools: [],
  active: null,
  lastJson: {},
  lastEdges: [],
  graph: { nodes: [], edges: [] },
  selectedAsset: null,
  selectedField: null,
};

const $ = (id) => document.getElementById(id);

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((el) => {
    el.classList.toggle("active", el.id === `tab-${name}`);
  });
  if (name === "graph") requestAnimationFrame(() => renderGraph(state.graph));
}

function setStatus(text, type = "") {
  const el = $("statusLine");
  el.textContent = text;
  el.className = `status ${type}`;
}

async function postTool(name, payload = {}) {
  const res = await fetch(`/api/tools/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data.result;
}

async function loadTools() {
  const res = await fetch("/api/tools");
  const data = await res.json();
  state.tools = data.tools;
  renderToolList();
  selectTool(state.tools[0].name);
  refreshHealth();
  loadAssets();
}

async function callAndRender(name, payload) {
  selectTool(name);
  $("payloadEditor").value = pretty(payload);
  await runActiveTool();
}

async function loadAssets() {
  const search = $("assetSearch").value.trim();
  try {
    const result = await postTool("list_assets", { search, limit: 500 });
    renderAssets(result.assets || []);
  } catch (err) {
    setStatus(err.message, "err");
  }
}

function renderAssets(assets) {
  const root = $("assetList");
  if (!assets.length) {
    root.innerHTML = `<div class="asset-item">暂无资产。先执行采集并确认边。</div>`;
    return;
  }
  root.innerHTML = assets.map((asset) => `
    <div class="asset-item ${state.selectedAsset === asset.asset_id ? "active" : ""}" data-id="${asset.asset_id}">
      <b>${asset.asset_type}</b>${asset.asset_id}
    </div>
  `).join("");
  root.querySelectorAll(".asset-item[data-id]").forEach((el) => {
    el.onclick = () => selectAsset(el.dataset.id);
  });
}

async function selectAsset(assetId) {
  state.selectedAsset = assetId;
  state.selectedField = null;
  $("selectedAsset").textContent = assetId;
  $("selectedField").textContent = "未选择字段";
  document.querySelectorAll(".asset-item").forEach((el) => el.classList.toggle("active", el.dataset.id === assetId));
  try {
    const result = await postTool("list_fields", { asset_id: assetId, limit: 1000 });
    renderFields(result.fields || []);
  } catch (err) {
    setStatus(err.message, "err");
  }
}

function renderFields(fields) {
  const root = $("fieldList");
  if (!fields.length) {
    root.innerHTML = `<div class="field-item">暂无字段</div>`;
    return;
  }
  root.innerHTML = fields.map((field) => `
    <div class="field-item ${state.selectedField === field.field_id ? "active" : ""}" data-id="${field.field_id}">
      ${field.column_name}
    </div>
  `).join("");
  root.querySelectorAll(".field-item[data-id]").forEach((el) => {
    el.onclick = () => selectField(el.dataset.id);
  });
}

function selectField(fieldId) {
  state.selectedField = fieldId;
  $("selectedField").textContent = fieldId;
  document.querySelectorAll(".field-item").forEach((el) => el.classList.toggle("active", el.dataset.id === fieldId));
}

function renderToolList() {
  const root = $("toolList");
  root.innerHTML = "";
  for (const tool of state.tools) {
    const item = document.createElement("div");
    item.className = "tool";
    item.dataset.name = tool.name;
    item.innerHTML = `<b>${tool.group}</b><span>${tool.name}</span>`;
    item.onclick = () => selectTool(tool.name);
    root.appendChild(item);
  }
}

function selectTool(name) {
  state.active = state.tools.find((t) => t.name === name);
  document.querySelectorAll(".tool").forEach((el) => el.classList.toggle("active", el.dataset.name === name));
  $("activeToolName").textContent = name;
  $("activeToolGroup").textContent = state.active.group;
  $("payloadEditor").value = pretty(state.active.params);
  setStatus("Ready");
}

async function runActiveTool() {
  if (!state.active) return;
  let payload;
  try {
    payload = JSON.parse($("payloadEditor").value || "{}");
  } catch (err) {
    setStatus(`JSON 参数错误: ${err.message}`, "err");
    return;
  }
  setStatus(`执行 ${state.active.name} ...`);
  const started = performance.now();
  try {
    const result = await postTool(state.active.name, payload);
    state.lastJson = result;
    $("jsonOutput").textContent = pretty(result);
    const edges = extractEdges(result);
    if (edges.length) {
      state.lastEdges = edges;
      state.graph = graphFromEdges(edges);
      renderEdges(edges);
      renderGraph(state.graph);
      switchTab("graph");
    } else if (result.nodes && result.edges) {
      state.lastEdges = result.edges;
      state.graph = normalizeGraph(result);
      renderEdges(result.edges);
      renderGraph(state.graph);
      switchTab("graph");
    }
    setStatus(`完成，用时 ${Math.round(performance.now() - started)}ms`, "ok");
    refreshHealth(false);
  } catch (err) {
    setStatus(err.message, "err");
  }
}

function extractEdges(value) {
  const edges = [];
  const visit = (node) => {
    if (!node) return;
    if (Array.isArray(node)) {
      node.forEach(visit);
      return;
    }
    if (typeof node === "object") {
      if (typeof node.source === "string" && typeof node.target === "string") edges.push(node);
      if (typeof node.source_field === "string" && typeof node.target_field === "string") {
        edges.push({ source: node.source_field, target: node.target_field, edge_type: node.edge_type, confidence: node.confidence });
      }
      if (typeof node.source_asset === "string" && typeof node.target_asset === "string") {
        edges.push({ source: node.source_asset, target: node.target_asset, edge_type: "TABLE" });
      }
      for (const child of Object.values(node)) visit(child);
    }
  };
  visit(value);
  const seen = new Set();
  return edges.filter((e) => {
    const key = `${e.source}->${e.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function graphFromEdges(edges) {
  const nodes = new Map();
  for (const edge of edges) {
    nodes.set(edge.source, { id: edge.source });
    nodes.set(edge.target, { id: edge.target });
  }
  return { nodes: [...nodes.values()], edges };
}

function subgraphForSeed(graph, seed, mode = "exact") {
  const match = (id) => mode === "prefix" ? id.startsWith(`${seed}.`) || id === seed : id === seed;
  const adjacency = new Map();
  for (const edge of graph.edges) {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
    adjacency.get(edge.source).push(edge.target);
    adjacency.get(edge.target).push(edge.source);
  }
  const seeds = graph.nodes.map((n) => n.id).filter(match);
  const visited = new Set(seeds);
  const queue = [...seeds];
  while (queue.length) {
    const node = queue.shift();
    for (const next of adjacency.get(node) || []) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  const edges = graph.edges.filter((edge) => visited.has(edge.source) && visited.has(edge.target));
  return graphFromEdges(edges);
}

async function loadProposedSubgraph(seed, mode) {
  const result = await postTool("export_full_lineage_graph", { include_proposed: true });
  const graph = normalizeGraph(result);
  const subgraph = subgraphForSeed(graph, seed, mode);
  state.lastJson = { seed, graph: subgraph };
  state.lastEdges = subgraph.edges;
  state.graph = subgraph;
  $("jsonOutput").textContent = pretty(state.lastJson);
  renderEdges(subgraph.edges);
  renderGraph(subgraph);
  switchTab("graph");
  setStatus(`展示 ${seed} 的 PROPOSED/CONFIRMED 图`, "ok");
}

function normalizeGraph(result) {
  return {
    nodes: result.nodes.map((id) => (typeof id === "string" ? { id } : id)),
    edges: result.edges.map((e) => ({ source: e.source, target: e.target, ...e })),
  };
}

function shortName(id) {
  const parts = id.split(".");
  if (parts.length >= 4) return `${parts.at(-2)}.${parts.at(-1)}`;
  if (parts.length >= 3) return `${parts.at(-2)}.${parts.at(-1)}`;
  return id;
}

function renderEdges(edges) {
  const root = $("edgeTable");
  if (!edges.length) {
    root.innerHTML = `<div class="empty-table">暂无血缘边。执行查询或选择左侧资产后查看。</div>`;
    return;
  }
  root.innerHTML = `
    <table>
      <colgroup>
        <col style="width: 31%">
        <col style="width: 31%">
        <col style="width: 12%">
        <col style="width: 9%">
        <col style="width: 9%">
        <col style="width: 8%">
      </colgroup>
      <thead>
        <tr>
          <th>Source</th>
          <th>Target</th>
          <th>Type</th>
          <th>Status</th>
          <th>Confidence</th>
          <th>Query</th>
        </tr>
      </thead>
      <tbody>
        ${edges.map((e) => {
          const confidence = e.confidence === undefined || e.confidence === null ? "" : Number(e.confidence).toFixed(2);
          return `
            <tr>
              <td><code title="${escapeHtml(e.source)}">${escapeHtml(e.source)}</code></td>
              <td><code title="${escapeHtml(e.target)}">${escapeHtml(e.target)}</code></td>
              <td>${escapeHtml(e.edge_type || "")}</td>
              <td class="muted">${escapeHtml(e.edge_status || "")}</td>
              <td>${escapeHtml(confidence)}</td>
              <td class="muted">${escapeHtml(e.query_id || e.edge_id || "")}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderGraph(graph) {
  const svg = $("graphSvg");
  const wrap = svg.getBoundingClientRect();
  const width = Math.max(wrap.width || 800, 600);
  const height = Math.max(wrap.height || 380, 360);
  const nodes = graph.nodes.map((n) => ({ ...n, type: n.id.split(".").length >= 4 ? "field" : "table" }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = graph.edges.filter((e) => byId.has(e.source) && byId.has(e.target));
  const indegree = new Map(nodes.map((n) => [n.id, 0]));
  for (const e of edges) indegree.set(e.target, (indegree.get(e.target) || 0) + 1);
  const queue = nodes.filter((n) => (indegree.get(n.id) || 0) === 0).map((n) => n.id);
  const depth = new Map(nodes.map((n) => [n.id, 0]));
  while (queue.length) {
    const id = queue.shift();
    for (const e of edges.filter((edge) => edge.source === id)) {
      depth.set(e.target, Math.max(depth.get(e.target) || 0, (depth.get(id) || 0) + 1));
      indegree.set(e.target, (indegree.get(e.target) || 0) - 1);
      if (indegree.get(e.target) === 0) queue.push(e.target);
    }
  }
  const layers = new Map();
  for (const n of nodes) {
    const d = depth.get(n.id) || 0;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(n);
  }
  const layerKeys = [...layers.keys()].sort((a, b) => a - b);
  const nodeW = 210;
  const nodeH = 42;
  const gapX = Math.max(250, (width - 180) / Math.max(1, layerKeys.length - 1));
  for (const d of layerKeys) {
    const layer = layers.get(d).sort((a, b) => a.id.localeCompare(b.id));
    const totalH = (layer.length - 1) * 72;
    layer.forEach((n, i) => {
      n.x = 80 + d * gapX;
      n.y = Math.max(48, height / 2 - totalH / 2 + i * 72);
    });
  }

  $("emptyGraph").style.display = nodes.length ? "none" : "grid";
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#73836b"></path>
      </marker>
    </defs>
    <g id="graphViewport">
    ${edges.map((e, index) => {
      const a = byId.get(e.source), b = byId.get(e.target);
      const x1 = a.x + nodeW;
      const y1 = a.y + nodeH / 2;
      const x2 = b.x;
      const y2 = b.y + nodeH / 2;
      const c = Math.max(60, Math.abs(x2 - x1) * .42);
      const path = `M ${x1} ${y1} C ${x1 + c} ${y1}, ${x2 - c} ${y2}, ${x2} ${y2}`;
      const proposed = e.edge_status === "PROPOSED" ? " proposed" : "";
      const label = e.edge_type || "";
      return `<path class="edge${proposed}" id="edge-${index}" d="${path}"><title>${e.source} -> ${e.target}</title></path>
        ${label ? `<text class="edge-label"><textPath href="#edge-${index}" startOffset="50%">${label}</textPath></text>` : ""}`;
    }).join("")}
    ${nodes.map((n) => {
      const proposed = edges.some((e) => (e.source === n.id || e.target === n.id) && e.edge_status === "PROPOSED") ? " proposed" : "";
      return `<g class="node ${n.type}${proposed}" data-id="${n.id}" transform="translate(${n.x},${n.y})">
        <rect width="${nodeW}" height="${nodeH}" rx="3"></rect>
        <text x="12" y="26">${shortName(n.id)}</text>
        <title>${n.id}</title>
      </g>`;
    }).join("")}
    </g>
  `;
  svg.querySelectorAll(".node").forEach((el) => {
    el.addEventListener("click", () => {
      $("nodeInspector").textContent = el.dataset.id;
    });
  });
  enableGraphPanZoom(svg);
}

function enableGraphPanZoom(svg) {
  const viewport = svg.querySelector("#graphViewport");
  if (!viewport) return;
  let scale = 1, tx = 0, ty = 0, dragging = false, last = null;
  const apply = () => viewport.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
  svg.onwheel = (event) => {
    event.preventDefault();
    scale = Math.max(.35, Math.min(2.5, scale + (event.deltaY < 0 ? .1 : -.1)));
    apply();
  };
  svg.onpointerdown = (event) => {
    dragging = true;
    last = { x: event.clientX, y: event.clientY };
    svg.setPointerCapture(event.pointerId);
  };
  svg.onpointermove = (event) => {
    if (!dragging || !last) return;
    tx += event.clientX - last.x;
    ty += event.clientY - last.y;
    last = { x: event.clientX, y: event.clientY };
    apply();
  };
  svg.onpointerup = () => { dragging = false; last = null; };
}

async function refreshHealth(showStatus = true) {
  try {
    const health = await postTool("lineage_health_check", {});
    const runs = (health.runs || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
    const edges = (health.edges || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
    const proposed = (health.edges || []).find((row) => row.edge_status === "PROPOSED")?.count || 0;
    $("metricRuns").textContent = runs;
    $("metricEdges").textContent = edges;
    $("metricProposed").textContent = proposed;
    if (showStatus) {
      state.lastJson = health;
      $("jsonOutput").textContent = pretty(health);
    }
  } catch (err) {
    if (showStatus) setStatus(err.message, "err");
  }
}

function copyText(text) {
  navigator.clipboard?.writeText(text);
}

$("runBtn").onclick = runActiveTool;
$("formatBtn").onclick = () => {
  try { $("payloadEditor").value = pretty(JSON.parse($("payloadEditor").value || "{}")); } catch (err) { setStatus(err.message, "err"); }
};
$("refreshHealth").onclick = () => refreshHealth(true);
$("fitGraphBtn").onclick = () => renderGraph(state.graph);
$("loadFullGraphBtn").onclick = async () => {
  selectTool("export_full_lineage_graph");
  $("payloadEditor").value = pretty({ include_proposed: $("includeProposedToggle").checked });
  await runActiveTool();
};
$("copyJsonBtn").onclick = () => copyText($("jsonOutput").textContent);
$("copyEdgesBtn").onclick = () => copyText(pretty(state.lastEdges));
$("refreshAssetsBtn").onclick = loadAssets;
$("assetSearch").oninput = () => {
  clearTimeout(state.assetTimer);
  state.assetTimer = setTimeout(loadAssets, 250);
};
$("tableLineageBtn").onclick = () => {
  if (!state.selectedAsset) return setStatus("请选择表", "err");
  if ($("includeProposedToggle").checked) return loadProposedSubgraph(state.selectedAsset, "prefix");
  callAndRender("trace_table_lineage", { asset_id: state.selectedAsset, direction: "both", depth: 5 });
};
$("tableFullBtn").onclick = () => {
  if (!state.selectedAsset) return setStatus("请选择表", "err");
  if ($("includeProposedToggle").checked) return loadProposedSubgraph(state.selectedAsset, "prefix");
  callAndRender("trace_full_table_lineage", { asset_id: state.selectedAsset });
};
$("columnLineageBtn").onclick = () => {
  if (!state.selectedField) return setStatus("请选择字段", "err");
  callAndRender("trace_column_lineage", { field_id: state.selectedField, direction: "both", depth: 5, include_proposed: $("includeProposedToggle").checked });
};
$("columnFullBtn").onclick = () => {
  if (!state.selectedField) return setStatus("请选择字段", "err");
  if ($("includeProposedToggle").checked) return loadProposedSubgraph(state.selectedField, "exact");
  callAndRender("trace_full_column_lineage", { field_id: state.selectedField });
};
$("impactBtn").onclick = () => {
  if (!state.selectedField) return setStatus("请选择字段", "err");
  callAndRender("analyze_change_impact", { field_id: state.selectedField, change_type: "modify" });
};
document.querySelectorAll(".tab-btn").forEach((el) => {
  el.onclick = () => switchTab(el.dataset.tab);
});

loadTools();
