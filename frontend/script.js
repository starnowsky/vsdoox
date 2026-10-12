const API = '';  // тот же origin
const PAGE_W = 11.0;
const PAGE_H = 8.5;
const SCALE = 100; // px на дюйм

function parseNodes(text) {
  return text.split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map(line => {
      const [id, label] = line.split('|').map(s => s.trim());
      return { id, label: label || id };
    });
}

function parseEdges(text) {
  return text.split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map(line => {
      const [from, to] = line.split('|').map(s => s.trim());
      return { from, to };
    });
}

function setStatus(msg, type = '') {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status ' + type;
}

async function fetchLayout() {
  const nodes = parseNodes(document.getElementById('nodes').value);
  const edges = parseEdges(document.getElementById('edges').value);
  const layout = document.getElementById('layout').value;

  const res = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges, layout }),
  });

  if (!res.ok) throw new Error('Ошибка предпросмотра');
  return { nodes, edges, positions: (await res.json()).positions };
}

function renderPreview({ nodes, edges, positions }) {
  const svg = document.getElementById('svg');
  svg.innerHTML = '';

  // Фон-страница
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('x', 0);
  bg.setAttribute('y', 0);
  bg.setAttribute('width', PAGE_W * SCALE);
  bg.setAttribute('height', PAGE_H * SCALE);
  bg.setAttribute('fill', 'white');
  bg.setAttribute('stroke', '#cbd5e0');
  svg.appendChild(bg);

  svg.setAttribute('viewBox', `0 0 ${PAGE_W * SCALE} ${PAGE_H * SCALE}`);

  const toSvg = (pos) => ({
    x: pos.x * SCALE,
    // Visio Y снизу вверх → SVG Y сверху вниз
    y: (PAGE_H - pos.y - pos.h) * SCALE,
    w: pos.w * SCALE,
    h: pos.h * SCALE,
  });

  // Рисуем связи
  for (const edge of edges) {
    const a = positions[edge.from];
    const b = positions[edge.to];
    if (!a || !b) continue;

    const ax = a.x + a.w / 2;
    const ay = a.y + a.h / 2;
    const bx = b.x + b.w / 2;
    const by = b.y + b.h / 2;

    const [p1, p2] = clipLine(ax, ay, bx, by, a, b);
    const s1 = toSvg({ x: p1.x, y: p1.y, w: 0, h: 0 });
    const s2 = toSvg({ x: p2.x, y: p2.y, w: 0, h: 0 });

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', s1.x);
    line.setAttribute('y1', s1.y);
    line.setAttribute('x2', s2.x);
    line.setAttribute('y2', s2.y);
    line.setAttribute('stroke', '#666');
    line.setAttribute('stroke-width', '1.5');
    line.setAttribute('marker-end', 'url(#arrow)');
    svg.appendChild(line);
  }

  // Маркер стрелки
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  defs.innerHTML = `
    <marker id="arrow" markerWidth="10" markerHeight="10"
            refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#666"/>
    </marker>`;
  svg.appendChild(defs);

  // Рисуем узлы
  for (const node of nodes) {
    const p = positions[node.id];
    if (!p) continue;
    const s = toSvg(p);

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', s.x);
    rect.setAttribute('y', s.y);
    rect.setAttribute('width', s.w);
    rect.setAttribute('height', s.h);
    rect.setAttribute('rx', 8);
    rect.setAttribute('fill', node.color || '#DAE8FC');
    rect.setAttribute('stroke', node.border || '#6C8EBF');
    rect.setAttribute('stroke-width', '1.5');
    svg.appendChild(rect);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', s.x + s.w / 2);
    text.setAttribute('y', s.y + s.h / 2);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('font-family', 'Segoe UI, sans-serif');
    text.setAttribute('font-size', '13');
    text.setAttribute('fill', '#333');
    text.textContent = node.label || node.id;
    svg.appendChild(text);
  }
}

function clipLine(ax, ay, bx, by, a, b) {
  const clip = (px, py, qx, qy, w, h) => {
    const dx = qx - px, dy = qy - py;
    if (dx === 0 && dy === 0) return { x: px, y: py };
    const tx = dx !== 0 ? (w / 2) / Math.abs(dx) : Infinity;
    const ty = dy !== 0 ? (h / 2) / Math.abs(dy) : Infinity;
    const t = Math.min(tx, ty);
    return { x: px + dx * t, y: py + dy * t };
  };
  return [clip(ax, ay, bx, by, a.w, a.h), clip(bx, by, ax, ay, b.w, b.h)];
}

async function preview() {
  try {
    setStatus('Расчёт...', '');
    const data = await fetchLayout();
    renderPreview(data);
    setStatus('OK', 'success');
  } catch (e) {
    setStatus(e.message, 'error');
  }
}

async function download() {
  try {
    setStatus('Генерация .vsdx...', '');
    const nodes = parseNodes(document.getElementById('nodes').value);
    const edges = parseEdges(document.getElementById('edges').value);
    const layout = document.getElementById('layout').value;
    const title = document.getElementById('title').value || 'Схема';

    if (!nodes.length) {
      setStatus('Добавьте хотя бы один узел', 'error');
      return;
    }

    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes, edges, layout, title }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Ошибка генерации');
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = title + '.vsdx';
    a.click();
    URL.revokeObjectURL(url);

    setStatus('Файл скачан', 'success');
  } catch (e) {
    setStatus(e.message, 'error');
  }
}

document.getElementById('previewBtn').addEventListener('click', preview);
document.getElementById('downloadBtn').addEventListener('click', download);

// Авто-предпросмотр при старте
preview();