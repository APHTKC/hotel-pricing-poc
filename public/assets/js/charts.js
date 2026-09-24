const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));

export function renderLineChart({
  root, legend, xValues, series, xLabel, title, locale = 'zh-TW', currency = 'TWD',
  hidden = new Set(), onToggle = null, emptyLabel = 'No data',
}) {
  const rootElement = typeof root === 'string' ? document.querySelector(root) : root;
  const legendElement = typeof legend === 'string' ? document.querySelector(legend) : legend;
  const available = series.filter(item => item.points.some(Number.isFinite));
  const visible = available.filter(item => !hidden.has(item.name));
  const values = visible.flatMap(item => item.points).filter(Number.isFinite);
  legendElement.innerHTML = available.map(item => `<button type="button" class="legend-item interactive${hidden.has(item.name) ? ' is-hidden' : ''}" aria-pressed="${!hidden.has(item.name)}" data-series="${escapeHtml(item.name)}"><span class="legend-dot" style="background:${item.color}"></span>${escapeHtml(item.name)}</button>`).join('');
  if (onToggle) legendElement.querySelectorAll('[data-series]').forEach(button => button.addEventListener('click', () => onToggle(button.dataset.series)));
  if (!xValues.length || !values.length) {
    rootElement.innerHTML = `<div class="empty">${escapeHtml(emptyLabel)}</div>`;
    return;
  }
  const W = 1000, H = 350, L = 86, R = 24, T = 22, B = 54;
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const yMin = Math.max(0, minimum * .82), yMax = maximum * 1.08 || 1;
  const x = index => xValues.length === 1 ? (L + W - R) / 2 : L + index * (W - L - R) / (xValues.length - 1);
  const y = value => T + (yMax - value) * (H - T - B) / (yMax - yMin || 1);
  const compact = value => new Intl.NumberFormat(locale, { style: 'currency', currency, notation: 'compact', maximumFractionDigits: 1 }).format(value);
  const full = value => new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
  const step = Math.max(1, Math.ceil(xValues.length / 7));
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(title)}">`;
  for (let index = 0; index < 5; index += 1) {
    const value = yMin + (yMax - yMin) * index / 4, position = y(value);
    svg += `<line x1="${L}" y1="${position}" x2="${W - R}" y2="${position}" stroke="#e2e2dc"/><text x="${L - 10}" y="${position + 4}" text-anchor="end" fill="#555" font-size="12">${escapeHtml(compact(value))}</text>`;
  }
  xValues.forEach((value, index) => { if (index % step === 0 || index === xValues.length - 1) svg += `<text x="${x(index)}" y="${H - 22}" text-anchor="middle" fill="#555" font-size="12">${escapeHtml(xLabel(value))}</text>`; });
  visible.forEach(item => {
    const segments = []; let segment = [];
    item.points.forEach((value, index) => { if (Number.isFinite(value)) segment.push({ value, index }); else if (segment.length) { segments.push(segment); segment = []; } });
    if (segment.length) segments.push(segment);
    svg += '<g class="chart-series">';
    segments.forEach(points => {
      const coordinates = points.map(point => `${x(point.index)},${y(point.value)}`).join(' ');
      svg += `<polyline class="chart-series-line" points="${coordinates}" fill="none" stroke="${item.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline class="chart-series-hit" points="${coordinates}" data-tooltip="${escapeHtml(item.name)}"/>`;
    });
    segments.flat().forEach(point => {
      const tooltip = `${item.name} · ${xLabel(xValues[point.index])} · ${full(point.value)}`;
      svg += `<circle class="chart-point" cx="${x(point.index)}" cy="${y(point.value)}" r="4" fill="${item.color}" stroke="#fff" stroke-width="1.5" data-tooltip="${escapeHtml(tooltip)}"><title>${escapeHtml(tooltip)}</title></circle>`;
    });
    svg += '</g>';
  });
  rootElement.innerHTML = `${svg}</svg><div class="chart-tooltip" role="status" hidden></div>`;
  const tooltip = rootElement.querySelector('.chart-tooltip');
  const show = event => { tooltip.textContent = event.currentTarget.dataset.tooltip; tooltip.hidden = false; const box = rootElement.getBoundingClientRect(); tooltip.style.left = `${event.clientX - box.left}px`; tooltip.style.top = `${event.clientY - box.top}px`; };
  rootElement.querySelectorAll('[data-tooltip]').forEach(element => { element.addEventListener('pointerenter', show); element.addEventListener('pointermove', show); element.addEventListener('pointerleave', () => { tooltip.hidden = true; }); });
}
