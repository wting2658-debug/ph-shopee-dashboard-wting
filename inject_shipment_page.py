#!/usr/bin/env python3
"""Canonical shipment templates; inject without changing other dashboard pages."""
import json
import re
from pathlib import Path

INDEX = Path(__file__).resolve().parent / "index.html"
DATA = INDEX.parent / "shipment_data.json"

CSS = """
    /* ===== Shipment Page ===== */
    #shipment-page .shipment-metrics-grid {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px;
    }
    #shipment-page .shipment-metric-card {
      background: #fff; border: 1px solid #b9d6f5; border-radius: 16px;
      padding: 20px; opacity: 1; filter: none; box-shadow: 0 3px 12px rgba(51,78,112,.05);
    }
    #shipment-page .shipment-metric-label { font-size: 14px; color: #52657c; font-weight: 700; margin-bottom: 10px; }
    #shipment-page .shipment-metric-value { font-size: 30px; line-height: 1.2; font-weight: 800; font-variant-numeric: tabular-nums; }
    #shipment-page .shipment-metric-sub { margin-top: 12px; font-size: 14px; color: #52657c; display: flex; gap: 10px; flex-wrap: wrap; }
    #shipment-page .shipment-metric-delta { font-weight: 700; }
    #shipment-page .table-panel { padding: 18px; }
    #shipment-page .table-wrap { overflow: auto; max-height: 760px; border: 1px solid #e2e9f1; border-radius: 10px; }
    #shipment-page .shipment-table { width: 100%; min-width: 1120px; table-layout: fixed; border-collapse: separate; border-spacing: 0; }
    #shipment-page .shipment-table th, #shipment-page .shipment-table td {
      width: auto; padding: 12px 12px; font-size: 15px; line-height: 1.5;
      text-align: right; vertical-align: middle; white-space: nowrap; overflow-wrap: normal;
      color: #263a53; border-left: 0; border-bottom: 1px solid #e5ebf2; font-variant-numeric: tabular-nums;
    }
    #shipment-page .shipment-table th { background: #f2f6fb; color: #334d69; font-size: 15px; font-weight: 700; position: sticky; top: 0; z-index: 2; }
    #shipment-page .shipment-table th.shipment-text, #shipment-page .shipment-table td.shipment-text { text-align: left; white-space: normal; word-break: break-word; }
    #shipment-page .shipment-table td:first-child { font-weight: 700; }
    #shipment-page .shipment-table tbody tr:nth-child(even) td { background: #fafcfe; }
    #shipment-page .shipment-table tbody tr:hover td { background: #f0f6fd; }
    #shipment-page .shipment-table tbody tr.is-selected td { background: #eaf3ff; }
    #shipment-page .shipment-table td.shipment-total { font-weight: 800; }
    #shipment-page .shipment-table td.shipment-compare { color: #52657c; }
    #shipment-page .shipment-table td.shipment-empty { text-align: center; padding: 32px; color: #667c93; }
    #shipment-page .shipment-cat-btn, #shipment-page .shipment-product-btn {
      font: inherit; font-weight: 700; cursor: pointer; text-align: left; vertical-align: middle;
      border: 0; border-radius: 6px; padding: 0; color: #1d6abb; background: transparent;
      white-space: normal; word-break: break-word; line-height: 1.5;
    }
    #shipment-page .shipment-cat-btn { padding: 4px 12px; border: 1px solid #b9d6f5; border-radius: 999px; background: #f0f7ff; white-space: nowrap; }
    #shipment-page .shipment-cat-btn.is-active { color: #fff; background: #2787e7; border-color: #2787e7; }
    #shipment-page .shipment-product-btn:hover { color: #0c4c91; text-decoration: underline; }
    #shipment-page .shipment-product-btn.is-active { color: #0c4c91; text-decoration: underline; }
    #shipment-page .shipment-chip-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
    #shipment-page .shipment-filter-chip { display: inline-flex; align-items: center; gap: 8px; padding: 5px 10px 5px 14px; color: #1d6abb; background: #edf5ff; border: 1px solid #b9d6f5; border-radius: 999px; font-size: 14px; font-weight: 700; }
    #shipment-page .shipment-filter-chip button { border: 0; background: #d9eaff; color: #1d6abb; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; padding: 0; font-size: 16px; }
    #shipment-page .shipment-filter-hint { font-size: 13px; color: #667c93; }
    #shipment-page .shipment-tri-chart { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
    #shipment-page .shipment-tri-chart .panel { padding: 16px; }
    #shipment-page .chart-wrap-inner { position: relative; height: 260px; }
    #shipment-page .shipment-chart-wrap { position: relative; height: 340px; }
    #shipment-page .shipment-sku-filter { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
    #shipment-page .shipment-sku-filter label { font-size: 14px; font-weight: 700; color: #44617f; }
    #shipment-page .shipment-sku-filter input { padding: 9px 12px; border: 1px solid #ccd9e7; border-radius: 8px; font-size: 15px; width: 280px; }
    #shipment-page .shipment-dim-switch { display: inline-flex; gap: 4px; padding: 4px; background: #f0f4f9; border: 1px solid #dbe4ee; border-radius: 10px; }
    #shipment-page .shipment-dim-switch button { border: 0; background: transparent; color: #52657c; font-size: 14px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
    #shipment-page .shipment-dim-switch button.is-active { background: #2787e7; color: #fff; }
    #shipment-page .delta-up { color: #15966a; }
    #shipment-page .delta-down { color: #df4f53; }
    #shipment-page .delta-flat { color: #667c93; }
    @media (max-width: 1180px) { #shipment-page .shipment-tri-chart { grid-template-columns: 1fr; } }
    @media (max-width: 860px) { #shipment-page .shipment-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
"""

HTML = """    <main class="dashboard-page" id="shipment-page" hidden>
      <section class="panel">
        <div class="panel-head"><div><h2 class="panel-title">渠道总出货指标</h2><div class="panel-subtitle" id="shipment-period-label"></div></div></div>
        <div class="shipment-chip-row" id="shipment-filter-row"></div>
        <div class="shipment-metrics-grid" id="shipment-metrics-grid"></div>
      </section>
      <section class="panel" style="margin-top:18px;">
        <div class="panel-head"><div><h2 class="panel-title">DMS · 品类出货量</h2><div class="panel-subtitle">按顶部查询日期和对比日期计算出货量及环比。点击品类联动指标、趋势和产品明细。</div></div></div>
        <div class="table-wrap"><table class="shipment-table" id="shipment-category-table"></table></div>
      </section>
      <section class="panel" style="margin-top:18px;">
        <div class="panel-head"><div><h2 class="panel-title">日趋势 · TT / 虾皮 / Lazada</h2><div class="panel-subtitle" id="shipment-daily-subtitle">查询日期段内每日出货量，支持品类与产品筛选。</div></div></div>
        <div class="shipment-tri-chart">
          <div class="panel"><h3 style="font-size:16px;margin-bottom:10px;color:#ee4d2d;">TT销量日趋势</h3><div class="chart-wrap-inner"><canvas id="chart-shipment-daily-tiktok"></canvas></div></div>
          <div class="panel"><h3 style="font-size:16px;margin-bottom:10px;color:#2787e7;">虾皮销量日趋势</h3><div class="chart-wrap-inner"><canvas id="chart-shipment-daily-shopee"></canvas></div></div>
          <div class="panel"><h3 style="font-size:16px;margin-bottom:10px;color:#f5a623;">Lazada销量日趋势</h3><div class="chart-wrap-inner"><canvas id="chart-shipment-daily-lazada"></canvas></div></div>
        </div>
      </section>
      <section class="panel table-panel" style="margin-top:18px;">
        <div class="panel-head"><div><h2 class="panel-title" id="shipment-detail-title">出货明细 · 按SKU货号汇总</h2><div class="panel-subtitle" id="shipment-detail-subtitle"></div></div></div>
        <div class="shipment-sku-filter">
          <div class="shipment-dim-switch" id="shipment-dim-switch" role="group" aria-label="出货明细维度">
            <button type="button" data-dim="sku" class="is-active">SKU货号</button><button type="button" data-dim="category">品类</button><button type="button" data-dim="name">产品名</button>
          </div>
          <label for="shipment-sku-search">搜索</label><input id="shipment-sku-search" type="text" placeholder="输入SKU、品类或产品名...">
        </div>
        <div class="table-wrap"><table class="shipment-table" id="shipment-sku-table"></table></div>
      </section>
      <section class="panel" style="margin-top:18px;">
        <div class="panel-head"><div><h2 class="panel-title">3渠道 · 月度出货趋势</h2><div class="panel-subtitle">展示历史各月实际出货量（非环比基数），支持品类与产品筛选；未完结月份为已到数累计。</div></div></div>
        <div class="shipment-chart-wrap"><canvas id="chart-shipment-trend"></canvas></div>
      </section>
      <section class="formula-note">出货分析口径：查询期与对比期均严格取顶部所选起止日期（含首尾日）；环比 =（查询期出货量 - 对比期出货量）/ 对比期出货量 × 100%。不以整个上月替代对比期；对比量为 0 且本期非 0 时显示“无基数”，两期均为 0 时显示 0.0%。明细包含仅在对比期有出货的产品，以免漏算基数。未到数日期不作补量。</section>
    </main>
"""

JS = """
    // ===== Shipment Page Rendering =====
    const SHIPMENT_STATE = { category: null, product: null, productDim: 'sku', dim: 'sku', search: '' };
    const SHIPMENT_CHANNELS = ['tiktok', 'shopee', 'lazada'];
    let SHIPMENT_PERIOD_CACHE = null;
    function shipmentEscape(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function formatShipmentNumber(n) { return (Number(n) || 0).toLocaleString('en-US'); }
    function shipmentDelta(current, prev) { return prev === 0 ? (current === 0 ? 0 : null) : (current - prev) / prev * 100; }
    function formatShipmentDelta(delta) {
      if (delta === null || !Number.isFinite(delta)) return '<span class="delta-flat" title="对比期出货量为0，无法计算百分比">无基数</span>';
      if (Math.abs(delta) < .05) return '<span class="delta-flat">0.0%</span>';
      return `<span class="${delta > 0 ? 'delta-up' : 'delta-down'}">${delta > 0 ? '↑' : '↓'} ${Math.abs(delta).toFixed(1)}%</span>`;
    }
    function shipmentPeriodData() {
      const key = [state.start, state.end, state.compareStart, state.compareEnd].join('|');
      if (SHIPMENT_PERIOD_CACHE?.key === key) return SHIPMENT_PERIOD_CACHE;
      const current = [], compare = [];
      for (const r of SHIPMENT_DATA.daily_records || []) {
        if (r[0] >= state.start && r[0] <= state.end) current.push(r);
        if (r[0] >= state.compareStart && r[0] <= state.compareEnd) compare.push(r);
      }
      SHIPMENT_PERIOD_CACHE = { key, current, compare };
      return SHIPMENT_PERIOD_CACHE;
    }
    function shipmentMatches(r, includeCategory = true) {
      const p = SHIPMENT_DATA.catalog[r[1]];
      return p && (!includeCategory || !SHIPMENT_STATE.category || p.category === SHIPMENT_STATE.category)
        && (!SHIPMENT_STATE.product || p[SHIPMENT_STATE.productDim] === SHIPMENT_STATE.product);
    }
    function shipmentSelectedRecords(records, includeCategory = true) { return records.filter(r => shipmentMatches(r, includeCategory)); }
    function shipmentSummary(records) {
      const sums = { total: 0, tiktok: 0, shopee: 0, lazada: 0 };
      for (const r of records) SHIPMENT_CHANNELS.forEach((ch, i) => { sums[ch] += r[i + 2]; sums.total += r[i + 2]; });
      return sums;
    }
    function shipmentBaseRows(includeCategory = true) {
      const period = shipmentPeriodData(), groups = new Map();
      function add(records, prev) {
        for (const r of shipmentSelectedRecords(records, includeCategory)) {
          if (!groups.has(r[1])) groups.set(r[1], { ...SHIPMENT_DATA.catalog[r[1]], total: 0, tiktok: 0, shopee: 0, lazada: 0, prev_total: 0, prev_tiktok: 0, prev_shopee: 0, prev_lazada: 0 });
          const g = groups.get(r[1]), prefix = prev ? 'prev_' : '';
          SHIPMENT_CHANNELS.forEach((ch, i) => { g[prefix + ch] += r[i + 2]; g[prefix + 'total'] += r[i + 2]; });
        }
      }
      add(period.current, false); add(period.compare, true);
      return Array.from(groups.values());
    }
    function shipmentGroupRows(rows, dim) {
      const groups = new Map();
      for (const r of rows) {
        const key = dim === 'category' ? r.category : dim === 'name' ? (r.name || r.sku) : r.sku;
        if (!groups.has(key)) groups.set(key, { key, sku: r.sku, name: r.name, category: r.category, categories: new Set(), total: 0, tiktok: 0, shopee: 0, lazada: 0, prev_total: 0, prev_tiktok: 0, prev_shopee: 0, prev_lazada: 0 });
        const g = groups.get(key); g.categories.add(r.category);
        for (const field of ['total', ...SHIPMENT_CHANNELS, 'prev_total', ...SHIPMENT_CHANNELS.map(c => 'prev_' + c)]) g[field] += r[field];
      }
      return Array.from(groups.values()).map(g => ({ ...g, category: Array.from(g.categories).join(' / ') })).sort((a, b) => b.total - a.total || b.prev_total - a.prev_total || a.key.localeCompare(b.key));
    }
    function renderShipmentFilterRow() {
      const chips = [];
      if (SHIPMENT_STATE.category) chips.push(`<span class="shipment-filter-chip">品类：${shipmentEscape(SHIPMENT_STATE.category)}<button type="button" data-shipment-clear="category" title="清除品类筛选">×</button></span>`);
      if (SHIPMENT_STATE.product) chips.push(`<span class="shipment-filter-chip">产品：${shipmentEscape(SHIPMENT_STATE.product)}<button type="button" data-shipment-clear="product" title="清除产品筛选">×</button></span>`);
      chips.push(`<span class="shipment-filter-hint">${chips.length ? '已按当前筛选展示清晰数据；点击 × 清除筛选' : '点击下方品类或产品可联动整页数据'}</span>`);
      document.getElementById('shipment-filter-row').innerHTML = chips.join('');
    }
    function renderShipmentMetrics() {
      const p = shipmentPeriodData();
      const curr = shipmentSummary(shipmentSelectedRecords(p.current));
      const prev = shipmentSummary(shipmentSelectedRecords(p.compare));
      const available = SHIPMENT_DATA.available_range;
      document.getElementById('shipment-period-label').textContent = `查询期：${state.start} ~ ${state.end}　对比期：${state.compareStart} ~ ${state.compareEnd}` + (available ? `　源数据截至 ${available.end}` : '');
      document.getElementById('shipment-metrics-grid').innerHTML = [['total','总出货','#ee4d2d'],['tiktok','TIKTOK','#ee4d2d'],['shopee','SHOPEE','#2787e7'],['lazada','LAZADA','#f5a623']].map(([key,label,color]) => `
        <div class="shipment-metric-card"><div class="shipment-metric-label">${label}</div><div class="shipment-metric-value" style="color:${color}">${formatShipmentNumber(curr[key])}</div><div class="shipment-metric-sub"><span>对比期 ${formatShipmentNumber(prev[key])}</span><span class="shipment-metric-delta">${formatShipmentDelta(shipmentDelta(curr[key],prev[key]))}</span></div></div>`).join('');
    }
    function shipmentCols(widths) { return '<colgroup>' + widths.map(w => `<col style="width:${w}%">`).join('') + '</colgroup>'; }
    function renderShipmentCategoryTable() {
      const groups = shipmentGroupRows(shipmentBaseRows(false), 'category');
      const total = groups.reduce((sum, g) => sum + g.total, 0);
      const headers = ['品类','总量','占比','环比','Tiktok','TT占比','TT环比','Shopee','SP占比','SP环比','Lazada','LZ占比','LZ环比'];
      const head = '<thead><tr>' + headers.map((h,i) => `<th${i === 0 ? ' class="shipment-text"' : ''}>${h}</th>`).join('') + '</tr></thead>';
      const body = groups.map(g => {
        const active = SHIPMENT_STATE.category === g.key;
        const channels = SHIPMENT_CHANNELS.map(ch => `<td>${formatShipmentNumber(g[ch])}</td><td>${(g.total ? g[ch] / g.total * 100 : 0).toFixed(1)}%</td><td>${formatShipmentDelta(shipmentDelta(g[ch], g['prev_' + ch]))}</td>`).join('');
        return `<tr${active ? ' class="is-selected"' : ''}><td class="shipment-text"><button type="button" class="shipment-cat-btn${active ? ' is-active' : ''}" data-shipment-category="${shipmentEscape(g.key)}">${shipmentEscape(g.key)}</button></td><td class="shipment-total">${formatShipmentNumber(g.total)}</td><td>${(total ? g.total / total * 100 : 0).toFixed(1)}%</td><td>${formatShipmentDelta(shipmentDelta(g.total,g.prev_total))}</td>${channels}</tr>`;
      }).join('');
      document.getElementById('shipment-category-table').innerHTML = shipmentCols([10,9,6,8,8,6,8,8,6,8,8,6,9]) + head + '<tbody>' + (body || '<tr><td colspan="13" class="shipment-empty">所选日期段没有出货记录</td></tr>') + '</tbody>';
    }
    function shipmentChart(canvasId, type, labels, datasets) {
      if (state.charts[canvasId]) state.charts[canvasId].destroy();
      state.charts[canvasId] = new Chart(document.getElementById(canvasId), { type, data: { labels, datasets }, options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', labels: { color: '#44617f', font: { size: 13, weight: '700' } } }, tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + formatShipmentNumber(ctx.parsed.y) } } },
        scales: { x: { ticks: { color: '#52657c', font: { size: 12 }, maxTicksLimit: 16 }, grid: { display: false } }, y: { ticks: { color: '#52657c', callback: v => formatShipmentNumber(v) }, grid: { color: '#e6edf5' } } }
      } });
    }
    function renderShipmentDailyCharts() {
      const rows = shipmentSelectedRecords(shipmentPeriodData().current), daily = new Map();
      // Include all requested days, including days without records, without inventing quantities.
      const start = new Date(state.start + 'T00:00:00Z'), end = new Date(state.end + 'T00:00:00Z');
      for (let d = start; d <= end; d = new Date(d.getTime() + 86400000)) daily.set(d.toISOString().slice(0,10), [0,0,0]);
      for (const r of rows) { if (!daily.has(r[0])) daily.set(r[0], [0,0,0]); r.slice(2,5).forEach((q,i) => daily.get(r[0])[i] += q); }
      const dates = Array.from(daily.keys()).sort();
      document.getElementById('shipment-daily-subtitle').textContent = `查询期 ${state.start} ~ ${state.end} 每日出货量；已按当前品类 / 产品筛选。`;
      [['tiktok','Tiktok','#ee4d2d'],['shopee','Shopee','#2787e7'],['lazada','Lazada','#f5a623']].forEach(([key,label,color],i) => shipmentChart('chart-shipment-daily-' + key, 'bar', dates, [{ label, data: dates.map(d => daily.get(d)[i]), backgroundColor: color, borderRadius: 5, maxBarThickness: 42 }]));
    }
    function renderShipmentTrendChart() {
      const monthly = new Map();
      for (const r of SHIPMENT_DATA.daily_records || []) {
        const ym = r[0].slice(0,7); if (!monthly.has(ym)) monthly.set(ym, [0,0,0]);
        if (shipmentMatches(r)) r.slice(2,5).forEach((q,i) => monthly.get(ym)[i] += q);
      }
      const months = Array.from(monthly.keys()).sort();
      shipmentChart('chart-shipment-trend', 'line', months, [['Tiktok','#ee4d2d'],['Shopee','#2787e7'],['Lazada','#f5a623']].map(([label,color],i) => ({ label, data: months.map(m => monthly.get(m)[i]), borderColor: color, backgroundColor: color, borderWidth: 2.5, tension: .25, pointRadius: 3, fill: false })));
    }
    function renderShipmentSkuTable() {
      const dim = SHIPMENT_STATE.dim, dimLabel = {sku:'SKU货号',category:'品类',name:'产品名'}[dim];
      let rows = shipmentBaseRows();
      if (SHIPMENT_STATE.search) { const q = SHIPMENT_STATE.search.toLowerCase(); rows = rows.filter(r => [r.sku,r.name,r.category].some(v => (v || '').toLowerCase().includes(q))); }
      const groups = shipmentGroupRows(rows, dim), total = groups.reduce((s,g) => s + g.total, 0);
      document.getElementById('shipment-detail-title').textContent = `出货明细 · 按${dimLabel}汇总`;
      document.getElementById('shipment-detail-subtitle').textContent = `查询期 ${state.start} ~ ${state.end} / 对比期 ${state.compareStart} ~ ${state.compareEnd} · 共 ${groups.length} 条（含仅对比期出货产品）。`;
      const headers = dim === 'sku' ? ['SKU货号','产品名','品类','总量','Tiktok','Shopee','Lazada','对比期','环比'] : dim === 'category' ? ['品类','总量','占比','Tiktok','Shopee','Lazada','对比期','环比'] : ['产品名','品类','总量','占比','Tiktok','Shopee','Lazada','对比期','环比'];
      const textCount = dim === 'sku' ? 3 : dim === 'name' ? 2 : 1;
      const head = '<thead><tr>' + headers.map((h,i) => `<th${i < textCount ? ' class="shipment-text"' : ''}>${h}</th>`).join('') + '</tr></thead>';
      const body = groups.map(g => {
        let prefix;
        if (dim === 'sku') prefix = `<td class="shipment-text">${shipmentEscape(g.key)}</td><td class="shipment-text"><button type="button" class="shipment-product-btn" data-shipment-product="${shipmentEscape(g.key)}" data-product-dim="sku">${shipmentEscape(g.name || g.key)}</button></td><td class="shipment-text">${shipmentEscape(g.category)}</td><td class="shipment-total">${formatShipmentNumber(g.total)}</td>`;
        else {
          const label = dim === 'category' ? `<button type="button" class="shipment-cat-btn${SHIPMENT_STATE.category === g.key ? ' is-active' : ''}" data-shipment-category="${shipmentEscape(g.key)}">${shipmentEscape(g.key)}</button>` : `<button type="button" class="shipment-product-btn" data-shipment-product="${shipmentEscape(g.key)}" data-product-dim="name">${shipmentEscape(g.key)}</button>`;
          prefix = `<td class="shipment-text">${label}</td>` + (dim === 'name' ? `<td class="shipment-text">${shipmentEscape(g.category)}</td>` : '') + `<td class="shipment-total">${formatShipmentNumber(g.total)}</td><td>${(total ? g.total / total * 100 : 0).toFixed(1)}%</td>`;
        }
        return `<tr>${prefix}${SHIPMENT_CHANNELS.map(ch => `<td>${formatShipmentNumber(g[ch])}</td>`).join('')}<td class="shipment-compare">${formatShipmentNumber(g.prev_total)}</td><td>${formatShipmentDelta(shipmentDelta(g.total,g.prev_total))}</td></tr>`;
      }).join('');
      const widths = dim === 'sku' ? [16,24,8,9,8,8,8,10,9] : dim === 'name' ? [28,8,10,7,9,9,9,10,10] : [22,13,9,11,11,11,12,11];
      document.getElementById('shipment-sku-table').innerHTML = shipmentCols(widths) + head + '<tbody>' + (body || `<tr><td colspan="${headers.length}" class="shipment-empty">没有符合日期和筛选条件的产品</td></tr>`) + '</tbody>';
    }
    function renderShipmentPage() {
      renderShipmentFilterRow(); renderShipmentMetrics(); renderShipmentCategoryTable(); renderShipmentDailyCharts(); renderShipmentSkuTable(); renderShipmentTrendChart();
    }
    function applyShipmentFilter() { renderShipmentPage(); }
    document.addEventListener('click', e => {
      const cat = e.target.closest('[data-shipment-category]');
      if (cat) { const key = cat.dataset.shipmentCategory; SHIPMENT_STATE.category = SHIPMENT_STATE.category === key ? null : key; SHIPMENT_STATE.product = null; applyShipmentFilter(); return; }
      const prod = e.target.closest('[data-shipment-product]');
      if (prod) { const key = prod.dataset.shipmentProduct, dim = prod.dataset.productDim || 'sku'; SHIPMENT_STATE.product = SHIPMENT_STATE.product === key && SHIPMENT_STATE.productDim === dim ? null : key; SHIPMENT_STATE.productDim = dim; applyShipmentFilter(); return; }
      const clear = e.target.closest('[data-shipment-clear]');
      if (clear) { if (clear.dataset.shipmentClear === 'category') { SHIPMENT_STATE.category = null; SHIPMENT_STATE.product = null; } else SHIPMENT_STATE.product = null; applyShipmentFilter(); return; }
      const dim = e.target.closest('#shipment-dim-switch button');
      if (dim) { SHIPMENT_STATE.dim = dim.dataset.dim; document.querySelectorAll('#shipment-dim-switch button').forEach(b => b.classList.toggle('is-active', b.dataset.dim === SHIPMENT_STATE.dim)); renderShipmentSkuTable(); }
    });
    document.addEventListener('input', e => { if (e.target.id === 'shipment-sku-search') { SHIPMENT_STATE.search = e.target.value; renderShipmentSkuTable(); } });
"""


def replace_span(text, start_marker, end_marker, new_block):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + new_block + text[end:]


def update_template(text):
    text = replace_span(text, "    /* ===== Shipment Page ===== */", "\n  </style>", CSS.lstrip("\n"))
    text = re.sub(r"(?:\s*</style>){2,}", "\n  </style>", text)
    text = replace_span(text, '    <main class="dashboard-page" id="shipment-page" hidden>', "\n  <script>", HTML.rstrip() + "\n\n")
    # Remove the shared date-control dimension row entirely from all four pages.
    text = re.sub(r'        <div class="shipment-dim-row" id="shipment-dim-row" hidden>.*?\n        </div>\n', '', text, count=1, flags=re.S)
    text = replace_span(text, "    // ===== Shipment Page Rendering =====", "    syncDateInputs();", JS.lstrip("\n"))
    text = re.sub(r"(?:    syncDateInputs\(\);\s*)+", "    syncDateInputs();\n", text)
    return text


def main():
    text = update_template(INDEX.read_text(encoding="utf-8"))
    data = json.dumps(json.loads(DATA.read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
    start = text.index("    const SHIPMENT_DATA = ")
    end = text.index(";\n", start)
    text = text[:start] + "    const SHIPMENT_DATA = " + data + text[end:]
    if 'id="shipment-dim-row"' in text or text.count("<script>") != 1 or text.count("</style>") != 1:
        raise SystemExit("Invalid dashboard structure")
    INDEX.write_text(text, encoding="utf-8")
    print(f"Shipment updated: {len(text):,} chars")


if __name__ == "__main__":
    main()
