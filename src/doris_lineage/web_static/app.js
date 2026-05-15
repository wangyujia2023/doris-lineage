const state = {
  tools: [],
  active: null,
  activeScope: "table",
  lastJson: {},
  lastEdges: [],
  graph: { nodes: [], edges: [] },
  selectedAsset: null,
  selectedField: null,
  chart: null,
};

const TOOL_DOCS = {
  ingest_doris_audit_table: "从 Doris audit_log 表按时间范围采集 SQL，解析后写入 PROPOSED 血缘边。",
  bootstrap_lineage_history: "从显式 SQL 事件数组回填历史血缘，适合离线回归或批量导入。",
  trace_table_lineage: "查询单表上游、下游或双向表级血缘，支持 depth。",
  trace_full_table_lineage: "查询表的全量上下游血缘，不限制固定深度。",
  trace_column_lineage: "查询字段上游、下游或双向列级血缘，可包含 PROPOSED 边。",
  trace_full_column_lineage: "查询字段全量上下游列级血缘。",
  export_full_lineage_graph: "导出当前 SQLite 中的全库血缘图节点和边，用于全局巡检。",
  explain_lineage_edge: "解释单条血缘边来自哪条 SQL、哪个用户、何时执行。",
  list_proposed_edges: "列出待核验的 PROPOSED 边，支持按资产前缀和置信度过滤。",
  review_edge: "批量确认或拒绝 PROPOSED 边，确认后进入查询默认图谱。",
  analyze_change_impact: "输入字段变更，返回下游影响范围和路径。",
  lineage_health_check: "查看采集健康状态、skip 统计、parse error 比例和 PROPOSED 积压。",
  asset_lineage_resource: "返回某个表的当前血缘摘要，用于 MCP Resource 上下文注入。",
  prompts: "返回辅助核验和影响分析的提示模板。",
  list_assets: "列出已入库资产，供页面选择表。",
  list_fields: "列出某个资产下的字段，供字段级血缘查询。",
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

function setStatus(text, type = "") {
  const el = $("statusLine");
  el.textContent = text;
  el.className = `toast ${type}`;
  $("statStatus").textContent = type === "err" ? "Error" : type === "ok" ? "OK" : "Running";
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((el) => {
    el.classList.toggle("active", el.id === `panel-${name}`);
  });
  if (name === "lineage") requestAnimationFrame(() => renderGraph(state.graph));
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
  state.tools = data.tools || [];
  renderToolList();
  selectTool("trace_column_lineage");
  await Promise.allSettled([refreshHealth(false), loadAssets()]);
}

async function refreshHealth(showJson = true) {
  try {
    const health = await postTool("lineage_health_check", {});
    const runs = health.total_runs ?? (health.runs || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
    const edges = (health.edges || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
    const proposed = health.proposed_backlog ?? (health.edges || []).find((row) => row.edge_status === "PROPOSED")?.count ?? 0;
    $("metricRuns").textContent = runs;
    $("metricEdges").textContent = edges;
    $("metricProposed").textContent = proposed;
    if (showJson) showJsonResult(health);
  } catch (err) {
    setStatus(err.message, "err");
  }
}

async function loadAssets() {
  const search = $("assetSearch").value.trim();
  try {
    const result = await postTool("list_assets", { search, limit: 600 });
    renderAssets(result.assets || []);
  } catch (err) {
    setStatus(err.message, "err");
  }
}

function renderAssets(assets) {
  const root = $("assetList");
  if (!assets.length) {
    root.innerHTML = `<div class="asset-item">暂无资产。先采集审计表或执行回归。</div>`;
    return;
  }
  root.innerHTML = assets.map((asset) => `
    <div class="asset-item ${state.selectedAsset === asset.asset_id ? "active" : ""}" data-id="${escapeHtml(asset.asset_id)}">
      <b>${escapeHtml(asset.asset_type)}</b>${escapeHtml(asset.asset_id)}
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
  $("selectedField").textContent = "未选择";
  updateTarget();
  document.querySelectorAll(".asset-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === assetId);
  });
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
    <div class="field-item ${state.selectedField === field.field_id ? "active" : ""}" data-id="${escapeHtml(field.field_id)}">
      ${escapeHtml(field.column_name)}
    </div>
  `).join("");
  root.querySelectorAll(".field-item[data-id]").forEach((el) => {
    el.onclick = () => selectField(el.dataset.id);
  });
}

function selectField(fieldId) {
  state.selectedField = fieldId;
  state.activeScope = "column";
  $("selectedField").textContent = fieldId;
  document.querySelectorAll(".field-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === fieldId);
  });
  updateScopeButtons();
  updateTarget();
}

function updateScopeButtons() {
  document.querySelectorAll(".seg").forEach((el) => {
    el.classList.toggle("active", el.dataset.scope === state.activeScope);
  });
}

function updateTarget() {
  const target = state.activeScope === "column" ? state.selectedField : state.selectedAsset;
  $("targetTitle").textContent = target || "请选择左侧表或字段";
  $("targetSubtitle").textContent = state.activeScope === "column"
    ? "字段级血缘用于定位指标来源、派生表达式和变更影响。"
    : "表级血缘用于查看数据集之间的上下游依赖和 ETL 流向。";
}

function renderToolList() {
  const root = $("toolList");
  root.innerHTML = state.tools.map((tool) => `
    <div class="tool" data-name="${escapeHtml(tool.name)}">
      <b>${escapeHtml(tool.group)}</b>
      <span>${escapeHtml(tool.name)}</span>
      <small>${escapeHtml(TOOL_DOCS[tool.name] || "MCP tool")}</small>
    </div>
  `).join("");
  root.querySelectorAll(".tool").forEach((el) => {
    el.onclick = () => selectTool(el.dataset.name);
  });
}

function selectTool(name) {
  state.active = state.tools.find((t) => t.name === name) || state.tools[0];
  if (!state.active) return;
  document.querySelectorAll(".tool").forEach((el) => {
    el.classList.toggle("active", el.dataset.name === state.active.name);
  });
  $("activeToolName").textContent = state.active.name;
  $("activeToolGroup").textContent = state.active.group;
  $("activeToolDesc").textContent = TOOL_DOCS[state.active.name] || "MCP tool";
  $("payloadEditor").value = pretty(materializeDefaultParams(state.active));
}

function materializeDefaultParams(tool) {
  const params = structuredClone(tool.params || {});
  if ("asset_id" in params && state.selectedAsset) params.asset_id = state.selectedAsset;
  if ("field_id" in params && state.selectedField) params.field_id = state.selectedField;
  if ("include_proposed" in params) params.include_proposed = $("includeProposedToggle").checked;
  if ("direction" in params) params.direction = $("directionSelect").value;
  if ("depth" in params) params.depth = Number($("depthInput").value || 5);
  return params;
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
  await runTool(state.active.name, payload);
}

async function runTool(name, payload) {
  setStatus(`执行 ${name} ...`);
  const started = performance.now();
  try {
    const result = await postTool(name, payload);
    showJsonResult(result);
    updateFromResult(result);
    setStatus(`完成 ${name}，用时 ${Math.round(performance.now() - started)}ms`, "ok");
    await refreshHealth(false);
    return result;
  } catch (err) {
    setStatus(err.message, "err");
    throw err;
  }
}

function showJsonResult(result) {
  state.lastJson = result;
  const text = pretty(result);
  $("jsonOutput").textContent = text;
  $("apiOutput").textContent = text;
}

function updateFromResult(result) {
  let graph = null;
  if (result?.nodes && result?.edges) {
    graph = normalizeGraph(result);
  } else {
    const edges = extractEdges(result);
    if (edges.length) graph = graphFromEdges(edges);
  }
  if (graph) {
    state.graph = graph;
    state.lastEdges = graph.edges;
    renderEdges(graph.edges);
    renderGraph(graph);
    switchTab("lineage");
  }
}

function extractEdges(value) {
  const edges = [];
  const visit = (node) => {
    if (!node) return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (typeof node !== "object") return;
    if (typeof node.source === "string" && typeof node.target === "string") {
      edges.push(node);
    }
    if (typeof node.source_field === "string" && typeof node.target_field === "string") {
      edges.push({
        source: node.source_field,
        target: node.target_field,
        edge_type: node.edge_type,
        edge_status: node.edge_status,
        confidence: node.confidence,
        query_id: node.query_id,
        transform_expr: node.transform_expr,
      });
    }
    if (typeof node.source_asset === "string" && typeof node.target_asset === "string") {
      edges.push({ source: node.source_asset, target: node.target_asset, edge_type: "TABLE" });
    }
    Object.values(node).forEach(visit);
  };
  visit(value);
  const seen = new Set();
  return edges.filter((edge) => {
    const key = `${edge.source}->${edge.target}:${edge.edge_type || ""}:${edge.query_id || ""}`;
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

function normalizeGraph(result) {
  return {
    nodes: (result.nodes || []).map((node) => typeof node === "string" ? { id: node } : node),
    edges: (result.edges || []).map((edge) => ({ source: edge.source, target: edge.target, ...edge })),
  };
}

function shortName(id) {
  const parts = String(id).split(".");
  if (parts.length >= 4) return `${parts.at(-2)}.${parts.at(-1)}`;
  if (parts.length >= 3) return `${parts.at(-2)}.${parts.at(-1)}`;
  return id;
}

function nodeKind(id) {
  return String(id).split(".").length >= 4 ? "字段" : "表";
}

function nodeCategory(id) {
  return nodeKind(id) === "字段" ? 1 : 0;
}

function renderGraph(graph) {
  if (!window.echarts) {
    $("emptyGraph").textContent = "ECharts 未加载，请检查网络或静态资源。";
    $("emptyGraph").style.display = "grid";
    return;
  }
  if (!state.chart) {
    state.chart = echarts.init($("lineageChart"), "dark");
    state.chart.on("click", (params) => {
      if (params.dataType === "node") {
        $("nodeInspector").innerHTML = `
          <b>${escapeHtml(params.data.name)}</b><br>
          类型：${escapeHtml(params.data.kind)}<br>
          度数：${escapeHtml(params.data.value ?? 0)}
        `;
      }
    });
  }
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  $("emptyGraph").style.display = nodes.length ? "none" : "grid";
  $("statNodes").textContent = nodes.length;
  $("statGraphEdges").textContent = edges.length;

  const degree = new Map();
  edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  });

  const selected = state.activeScope === "column" ? state.selectedField : state.selectedAsset;
  const chartNodes = nodes.map((node) => {
    const id = node.id || node.name;
    const isSelected = selected && (id === selected || id.startsWith(`${selected}.`));
    return {
      id,
      name: shortName(id),
      fullName: id,
      kind: nodeKind(id),
      value: degree.get(id) || 1,
      category: nodeCategory(id),
      symbolSize: isSelected ? 46 : Math.max(22, Math.min(42, 18 + (degree.get(id) || 1) * 2.2)),
      itemStyle: isSelected ? { borderColor: "#f59e0b", borderWidth: 3 } : undefined,
      label: { show: true },
    };
  });

  const chartEdges = edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    value: edge.edge_type || "",
    lineStyle: {
      color: edge.edge_status === "PROPOSED" ? "#f59e0b" : "#64748b",
      width: edge.edge_status === "PROPOSED" ? 1.8 : 1.2,
      curveness: .18,
      type: edge.edge_status === "PROPOSED" ? "dashed" : "solid",
      opacity: .72,
    },
    label: {
      show: Boolean(edge.edge_type),
      formatter: edge.edge_type || "",
      color: "#94a3b8",
      fontSize: 10,
    },
    tooltip: {
      formatter: [
        `<b>${escapeHtml(edge.edge_type || "EDGE")}</b>`,
        `Source: ${escapeHtml(edge.source)}`,
        `Target: ${escapeHtml(edge.target)}`,
        `Status: ${escapeHtml(edge.edge_status || "")}`,
        `Confidence: ${escapeHtml(edge.confidence ?? "")}`,
        edge.transform_expr ? `Expr: ${escapeHtml(edge.transform_expr)}` : "",
      ].filter(Boolean).join("<br>"),
    },
  }));

  state.chart.setOption({
    backgroundColor: "transparent",
    color: ["#3b82f6", "#00c4b4"],
    animationDuration: 900,
    animationEasingUpdate: "quarticInOut",
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(10,22,40,.94)",
      borderColor: "rgba(255,255,255,.14)",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: (params) => {
        if (params.dataType === "edge") return params.data.tooltip?.formatter || "";
        return `<b>${escapeHtml(params.data.fullName)}</b><br>类型：${escapeHtml(params.data.kind)}<br>连接数：${escapeHtml(params.data.value)}`;
      },
    },
    legend: [{
      data: ["表", "字段"],
      top: 12,
      left: 20,
      textStyle: { color: "#94a3b8" },
    }],
    series: [{
      type: "graph",
      layout: "force",
      roam: true,
      draggable: true,
      focusNodeAdjacency: true,
      categories: [{ name: "表" }, { name: "字段" }],
      data: chartNodes,
      links: chartEdges,
      edgeSymbol: ["none", "arrow"],
      edgeSymbolSize: [0, 8],
      label: {
        position: "right",
        formatter: "{b}",
        color: "#e2e8f0",
        fontSize: 11,
      },
      emphasis: {
        focus: "adjacency",
        lineStyle: { width: 3, opacity: 1 },
      },
      force: {
        repulsion: 260,
        gravity: .06,
        edgeLength: [80, 230],
        friction: .42,
      },
      lineStyle: {
        color: "#64748b",
        opacity: .62,
      },
    }],
  }, true);
}

function renderEdges(edges) {
  const root = $("edgeTable");
  if (!edges.length) {
    root.innerHTML = `<div class="empty-table">暂无血缘边。执行查询后查看。</div>`;
    return;
  }
  root.innerHTML = `
    <table>
      <colgroup>
        <col style="width: 28%">
        <col style="width: 28%">
        <col style="width: 11%">
        <col style="width: 9%">
        <col style="width: 9%">
        <col style="width: 15%">
      </colgroup>
      <thead>
        <tr>
          <th>Source</th>
          <th>Target</th>
          <th>Type</th>
          <th>Status</th>
          <th>Confidence</th>
          <th>Query / Expr</th>
        </tr>
      </thead>
      <tbody>
        ${edges.map((edge) => {
          const confidence = edge.confidence === undefined || edge.confidence === null ? "" : Number(edge.confidence).toFixed(2);
          return `
            <tr>
              <td><code title="${escapeHtml(edge.source)}">${escapeHtml(edge.source)}</code></td>
              <td><code title="${escapeHtml(edge.target)}">${escapeHtml(edge.target)}</code></td>
              <td>${escapeHtml(edge.edge_type || "")}</td>
              <td class="muted">${escapeHtml(edge.edge_status || "")}</td>
              <td>${escapeHtml(confidence)}</td>
              <td class="muted" title="${escapeHtml(edge.transform_expr || "")}">${escapeHtml(edge.query_id || edge.transform_expr || edge.edge_id || "")}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
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
  const seeds = graph.nodes.map((node) => node.id).filter(match);
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
  const result = await runTool("export_full_lineage_graph", { include_proposed: true });
  const subgraph = subgraphForSeed(normalizeGraph(result), seed, mode);
  showJsonResult({ seed, graph: subgraph });
  state.graph = subgraph;
  state.lastEdges = subgraph.edges;
  renderEdges(subgraph.edges);
  renderGraph(subgraph);
  switchTab("lineage");
}

async function runLineageQuery(full = false) {
  const includeProposed = $("includeProposedToggle").checked;
  const direction = $("directionSelect").value;
  const depth = Number($("depthInput").value || 5);
  if (state.activeScope === "table") {
    if (!state.selectedAsset) return setStatus("请先选择表", "err");
    if (includeProposed) return loadProposedSubgraph(state.selectedAsset, "prefix");
    return runTool(full ? "trace_full_table_lineage" : "trace_table_lineage", full
      ? { asset_id: state.selectedAsset }
      : { asset_id: state.selectedAsset, direction, depth });
  }
  if (!state.selectedField) return setStatus("请先选择字段", "err");
  if (full && includeProposed) return loadProposedSubgraph(state.selectedField, "exact");
  return runTool(full ? "trace_full_column_lineage" : "trace_column_lineage", full
    ? { field_id: state.selectedField }
    : { field_id: state.selectedField, direction, depth, include_proposed: includeProposed });
}

function copyText(text) {
  navigator.clipboard?.writeText(text);
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((el) => {
    el.onclick = () => switchTab(el.dataset.tab);
  });
  document.querySelectorAll(".seg").forEach((el) => {
    el.onclick = () => {
      state.activeScope = el.dataset.scope;
      updateScopeButtons();
      updateTarget();
    };
  });
  $("refreshAssetsBtn").onclick = loadAssets;
  $("assetSearch").oninput = () => {
    clearTimeout(state.assetTimer);
    state.assetTimer = setTimeout(loadAssets, 250);
  };
  $("refreshHealth").onclick = () => refreshHealth(true);
  $("runIngestBtn").onclick = () => {
    selectTool("ingest_doris_audit_table");
    switchTab("api");
  };
  $("traceBtn").onclick = () => runLineageQuery(false);
  $("fullTraceBtn").onclick = () => runLineageQuery(true);
  $("impactBtn").onclick = () => {
    if (!state.selectedField) return setStatus("影响分析需要先选择字段", "err");
    runTool("analyze_change_impact", { field_id: state.selectedField, change_type: "modify" });
  };
  $("loadFullGraphBtn").onclick = () => runTool("export_full_lineage_graph", { include_proposed: $("includeProposedToggle").checked });
  $("fitGraphBtn").onclick = () => renderGraph(state.graph);
  $("focusSelectedBtn").onclick = () => {
    if (!state.selectedAsset && !state.selectedField) return setStatus("请先选择表或字段", "err");
    const seed = state.activeScope === "column" ? state.selectedField : state.selectedAsset;
    const mode = state.activeScope === "column" ? "exact" : "prefix";
    const subgraph = subgraphForSeed(state.graph, seed, mode);
    state.graph = subgraph;
    state.lastEdges = subgraph.edges;
    renderEdges(subgraph.edges);
    renderGraph(subgraph);
  };
  $("formatBtn").onclick = () => {
    try {
      $("payloadEditor").value = pretty(JSON.parse($("payloadEditor").value || "{}"));
    } catch (err) {
      setStatus(err.message, "err");
    }
  };
  $("runBtn").onclick = runActiveTool;
  $("copyJsonBtn").onclick = () => copyText($("jsonOutput").textContent);
  $("copyEdgesBtn").onclick = () => copyText(pretty(state.lastEdges));
  window.addEventListener("resize", () => state.chart?.resize());
}

wireEvents();
loadTools();
