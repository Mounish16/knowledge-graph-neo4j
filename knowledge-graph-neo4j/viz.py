"""
viz.py
------
Exports a KnowledgeGraph to a single, self-contained HTML file you can open
directly in a browser -- no server, no CDN, no npm install. The force-directed
layout and rendering are done with plain vanilla JavaScript + <canvas>.

Usage:
    from viz import export_html
    export_html(kg, "graph.html")
"""

from __future__ import annotations

import json

from knowledge_graph import KnowledgeGraph


# a small fixed palette keyed by entity "type" attribute, with a fallback.
# Ordered warm -> cool to follow the traceability chain from customer
# request down to module design, so the layer of a node is readable from
# its colour alone. Safety and verification are deliberately set apart
# from their neighbours, since those are the two an assessor looks for.
_TYPE_COLORS = {
    "customer_request":   "#E03131",  # red     -- where everything originates
    "stakeholder_need":   "#F76707",  # orange
    "system_requirement": "#F59F00",  # amber
    "safety_requirement": "#C2255C",  # magenta -- set apart on purpose
    "hlr":                "#2F9E44",  # green
    "llr":                "#66A80F",  # lime
    "hld":                "#1971C2",  # blue
    "lld":                "#4C6EF5",  # indigo
    "module_design":      "#7048E8",  # violet  -- the delivered end of the chain
    "verification":       "#0CA678",  # teal    -- evidence, not a requirement
    "_default":           "#868E96",
}


def _node_color(kg: KnowledgeGraph, entity: str) -> str:
    entity_type = kg.entity_attrs.get(entity, {}).get("type", "_default")
    return _TYPE_COLORS.get(entity_type, _TYPE_COLORS["_default"])


def export_html(kg: KnowledgeGraph, path: str, title: str = "Knowledge Graph") -> None:
    nodes = [
        {"id": name, "label": name, "color": _node_color(kg, name),
         "type": kg.entity_attrs.get(name, {}).get("type", "unknown")}
        for name in kg.entities()
    ]
    links = [
        {"source": s, "target": o, "label": p}
        for s, p, o in sorted(kg.triples)
    ]

    data_json = json.dumps({"nodes": nodes, "links": links})

    html = _HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data_json)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<style>
  html, body { margin: 0; height: 100%; background: #0f1115; font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; }
  #wrap { position: relative; width: 100%; height: 100%; }
  canvas { display: block; cursor: grab; }
  #title {
    position: absolute; top: 16px; left: 20px; color: #e8eaed;
    font-size: 18px; font-weight: 600; letter-spacing: 0.2px;
  }
  #legend {
    position: absolute; bottom: 16px; left: 20px; color: #cfd2d6; font-size: 12px;
    background: rgba(255,255,255,0.06); padding: 8px 12px; border-radius: 8px;
    line-height: 1.6;
  }
  .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
  #tooltip {
    position: absolute; pointer-events: none; background: #1c1f26; color: #f1f3f5;
    border: 1px solid #3a3f4b; padding: 6px 10px; border-radius: 6px; font-size: 12px;
    display: none; max-width: 260px;
  }
  #hint { position: absolute; top: 16px; right: 20px; color: #8b909a; font-size: 12px; }
</style>
</head>
<body>
<div id="wrap">
  <canvas id="c"></canvas>
  <div id="title">__TITLE__</div>
  <div id="hint">drag nodes &middot; scroll to zoom &middot; drag background to pan</div>
  <div id="legend"></div>
  <div id="tooltip"></div>
</div>
<script>
const DATA = __DATA__;

const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const legendEl = document.getElementById('legend');

function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

// ---- build node/link objects with simple physics state ----
const nodesById = {};
const nodes = DATA.nodes.map((n, i) => {
  const angle = (i / DATA.nodes.length) * Math.PI * 2;
  const node = {
    ...n,
    x: canvas.width / 2 + Math.cos(angle) * 150,
    y: canvas.height / 2 + Math.sin(angle) * 150,
    vx: 0, vy: 0,
  };
  nodesById[n.id] = node;
  return node;
});
const links = DATA.links.map(l => ({ ...l, source: nodesById[l.source], target: nodesById[l.target] }));

// legend, derived from distinct node types actually present
const seenTypes = {};
nodes.forEach(n => { seenTypes[n.type] = n.color; });
legendEl.innerHTML = Object.entries(seenTypes)
  .map(([type, color]) => `<div><span class="swatch" style="background:${color}"></span>${type}</div>`)
  .join('');

// ---- simple force simulation (repulsion + springs + centering) ----
const REPULSION = 6000;
const SPRING_LEN = 140;
const SPRING_K = 0.02;
const CENTER_K = 0.01;
const DAMPING = 0.85;

function step() {
  const cx = canvas.width / 2, cy = canvas.height / 2;

  for (const n of nodes) {
    if (n.dragging) continue;
    let fx = 0, fy = 0;

    // repulsion between all pairs
    for (const other of nodes) {
      if (other === n) continue;
      let dx = n.x - other.x, dy = n.y - other.y;
      let distSq = dx * dx + dy * dy || 0.01;
      let dist = Math.sqrt(distSq);
      let force = REPULSION / distSq;
      fx += (dx / dist) * force;
      fy += (dy / dist) * force;
    }

    // gentle pull toward center so the graph doesn't drift off-screen
    fx += (cx - n.x) * CENTER_K;
    fy += (cy - n.y) * CENTER_K;

    n.vx = (n.vx + fx) * DAMPING;
    n.vy = (n.vy + fy) * DAMPING;
  }

  // springs along edges
  for (const l of links) {
    let dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
    let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
    let stretch = dist - SPRING_LEN;
    let force = stretch * SPRING_K;
    let fx = (dx / dist) * force, fy = (dy / dist) * force;
    if (!l.source.dragging) { l.source.vx += fx; l.source.vy += fy; }
    if (!l.target.dragging) { l.target.vx -= fx; l.target.vy -= fy; }
  }

  for (const n of nodes) {
    if (n.dragging) continue;
    n.x += n.vx * 0.06;
    n.y += n.vy * 0.06;
  }
}

// ---- camera (pan/zoom) ----
const camera = { x: 0, y: 0, scale: 1 };

function toScreen(x, y) {
  return [(x + camera.x) * camera.scale, (y + camera.y) * camera.scale];
}
function toWorld(x, y) {
  return [x / camera.scale - camera.x, y / camera.scale - camera.y];
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();

  // links
  ctx.lineWidth = 1;
  for (const l of links) {
    const [sx, sy] = toScreen(l.source.x, l.source.y);
    const [tx, ty] = toScreen(l.target.x, l.target.y);
    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(tx, ty);
    ctx.stroke();

    // predicate label at midpoint
    const mx = (sx + tx) / 2, my = (sy + ty) / 2;
    ctx.fillStyle = 'rgba(210,215,222,0.65)';
    ctx.font = `${11 * camera.scale}px sans-serif`;
    ctx.fillText(l.label, mx, my);
  }

  // nodes
  for (const n of nodes) {
    const [x, y] = toScreen(n.x, n.y);
    const r = 10 * camera.scale;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = n.color;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(255,255,255,0.5)';
    ctx.stroke();

    ctx.fillStyle = '#f1f3f5';
    ctx.font = `${12 * camera.scale}px sans-serif`;
    ctx.fillText(n.label, x + r + 4, y + 4);
  }

  ctx.restore();
}

function loop() {
  step();
  draw();
  requestAnimationFrame(loop);
}
loop();

// ---- interaction: drag nodes, drag background to pan, wheel to zoom ----
let draggedNode = null;
let panning = false;
let lastMouse = null;

function findNodeAt(mx, my) {
  const [wx, wy] = toWorld(mx, my);
  for (const n of nodes) {
    const dx = n.x - wx, dy = n.y - wy;
    if (Math.sqrt(dx * dx + dy * dy) < 14) return n;
  }
  return null;
}

canvas.addEventListener('mousedown', e => {
  const mx = e.clientX, my = e.clientY;
  const n = findNodeAt(mx, my);
  if (n) {
    draggedNode = n;
    n.dragging = true;
    canvas.style.cursor = 'grabbing';
  } else {
    panning = true;
    lastMouse = [mx, my];
    canvas.style.cursor = 'grabbing';
  }
});

canvas.addEventListener('mousemove', e => {
  const mx = e.clientX, my = e.clientY;
  if (draggedNode) {
    const [wx, wy] = toWorld(mx, my);
    draggedNode.x = wx;
    draggedNode.y = wy;
    draggedNode.vx = 0;
    draggedNode.vy = 0;
  } else if (panning) {
    camera.x += (mx - lastMouse[0]) / camera.scale;
    camera.y += (my - lastMouse[1]) / camera.scale;
    lastMouse = [mx, my];
  } else {
    const n = findNodeAt(mx, my);
    if (n) {
      tooltip.style.display = 'block';
      tooltip.style.left = (mx + 12) + 'px';
      tooltip.style.top = (my + 12) + 'px';
      const out = links.filter(l => l.source === n).map(l => `${l.label} -> ${l.target.label}`);
      const inc = links.filter(l => l.target === n).map(l => `${l.source.label} -> (${l.label}) this`);
      tooltip.innerHTML = `<b>${n.label}</b> <i>(${n.type})</i><br>` + out.concat(inc).join('<br>');
    } else {
      tooltip.style.display = 'none';
    }
  }
});

window.addEventListener('mouseup', () => {
  if (draggedNode) draggedNode.dragging = false;
  draggedNode = null;
  panning = false;
  canvas.style.cursor = 'grab';
});

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  camera.scale = Math.max(0.2, Math.min(3, camera.scale * factor));
}, { passive: false });
</script>
</body>
</html>
"""
