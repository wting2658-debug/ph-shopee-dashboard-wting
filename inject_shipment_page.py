#!/usr/bin/env python3
"""
Inject / rebuild the "出货分析" (shipment) section of index.html.

Changes applied:
  1. Shipment numbers render as raw integers (no k / w abbreviation).
  2. A dimension segmented control (SKU货号 / 品类 / 产品名) is inserted
     below the date controls.
  3. Full-page data linkage: clicking a category in the DMS table filters
     the metric cards, charts and the detail table; clicking a product row
     filters further. A breadcrumb chip shows and resets the filter.
  4. Daily trend is split into 3 channels (TT / 虾皮 / Lazada) and moved
     above; the 3-channel monthly trend moves to the bottom of the page.

Run:  python inject_shipment_page.py
"""
import json
import re
from pathlib import Path

INDEX = Path(__file__).resolve().parent / "index.html"
DATA = Path(__file__).resolve().parent / "shipment_data.json"

# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
CSS = """
    /* ===== Shipment Page ===== */
    .shipment-metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .shipment-metric-card {
      background: var(--paper);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: var(--radius-xl);
      padding: 18px 20px;
      transition: box-shadow .2s ease, transform .2s ease, border-color .2s ease;
    }
    .shipment-metric-card.is-dimmed { opacity: .38; }
    .shipment-metric-card.is-active {
      border-color: #2787e7;
      box-shadow: 0 0 0 2px rgba(39,135,231,.18), var(--shadow);
    }
    .shipment-metric-label {
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #7c6f63;
      margin-bottom: 8px;
      font-weight: 700;
    }
    .shipment-metric-value {
      font-family: "Plus Jakarta Sans", "Noto Sans SC", sans-serif;
      font-size: 28px;
      font-weight: 800;
      line-height: 1;
      color: var(--ink);
    }
    .shipment-metric-sub {
      margin-top: 10px;
      font-size: 12px;
      color: var(--muted);
    }
    .shipment-metric-delta {
      display: inline-block;
      margin-left: 6px;
      font-size: 13px;
      font-weight: 700;
    }
    .shipment-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .shipment-table th,
    .shipment-table td {
      padding: 9px 10px;
      text-align: right;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }
    .shipment-table th {
      font-size: 12px;
      font-weight: 700;
      color: #6b5f54;
      background: rgba(61,42,17,.03);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .shipment-table td:first-child,
    .shipment-table th:first-child {
      text-align: left;
      position: sticky;
      left: 0;
      background: var(--paper);
      z-index: 2;
    }
    .shipment-table th:first-child { background: rgba(61,42,17,.03); z-index: 3; }
    .shipment-table tbody tr:hover { background: rgba(39,135,231,.06); }
    .shipment-cat-btn {
      border: 1px solid rgba(39,135,231,.35);
      background: rgba(39,135,231,.08);
      color: #1f6fc4;
      border-radius: 999px;
      padding: 3px 12px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      font-family: inherit;
      transition: background .16s ease, color .16s ease, border-color .16s ease;
    }
    .shipment-cat-btn:hover { background: rgba(39,135,231,.2); }
    .shipment-cat-btn.is-active {
      background: #2787e7;
      border-color: #2787e7;
      color: #fff;
    }
    .shipment-chip-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }
    .shipment-filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid rgba(39,135,231,.35);
      background: rgba(39,135,231,.1);
      color: #1f6fc4;
      border-radius: 999px;
      padding: 5px 8px 5px 14px;
      font-size: 13px;
      font-weight: 700;
    }
    .shipment-filter-chip button {
      border: none;
      background: rgba(31,111,196,.16);
      color: inherit;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      cursor: pointer;
      font-size: 13px;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
    }
    .shipment-filter-chip button:hover { background: #2787e7; color: #fff; }
    .shipment-filter-hint { font-size: 12px; color: var(--muted); }
    .shipment-chart-wrap {
      position: relative;
      height: 340px;
    }
    .shipment-tri-chart {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }
    .shipment-tri-chart .panel {
      padding: 16px;
    }
    .shipment-tri-chart .chart-wrap-inner {
      position: relative;
      height: 260px;
    }
    .shipment-dim-switch {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px;
      background: rgba(61,42,17,.05);
      border: 1px solid var(--line);
      border-radius: 999px;
    }
    .shipment-dim-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px dashed var(--line);
    }
    .shipment-dim-row[hidden] { display: none; }
    .shipment-dim-row-label {
      font-size: 13px;
      font-weight: 700;
      color: #44617f;
      white-space: nowrap;
    }
    .shipment-dim-switch button {
      border: none;
      background: transparent;
      color: #6b5f54;
      font-size: 13px;
      font-weight: 700;
      font-family: inherit;
      padding: 6px 16px;
      border-radius: 999px;
      cursor: pointer;
      transition: background .16s ease, color .16s ease;
    }
    .shipment-dim-switch button:hover { color: #1f6fc4; }
    .shipment-dim-switch button.is-active {
      background: #2787e7;
      color: #fff;
      box-shadow: 0 1px 4px rgba(39,135,231,.35);
    }
    .shipment-sku-filter {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .shipment-sku-filter input {
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 14px;
      width: 240px;
    }
    .shipment-sku-filter label {
      font-size: 13px;
      font-weight: 700;
      color: #44617f;
      white-space: nowrap;
    }
    .shipment-product-btn {
      border: none;
      background: transparent;
      color: #2787e7;
      font-size: 14px;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      padding: 2px 4px;
      border-radius: 6px;
      text-align: left;
    }
    .shipment-product-btn:hover { background: rgba(39,135,231,.12); }
    .shipment-product-btn.is-active { background: #2787e7; color: #fff; }
    @media (max-width: 1180px) {
      .shipment-tri-chart { grid-template-columns: 1fr; }
    }
    @media (max-width: 860px) {
      .shipment-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
"""

# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
HTML = """    <main class="dashboard-page" id="shipment-page" hidden>
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">渠道总出货指标</h2>
            <div class="panel-subtitle" id="shipment-period-label"></div>
          </div>
        </div>
        <div class="shipment-chip-row" id="shipment-filter-row"></div>
        <div class="shipment-metrics-grid" id="shipment-metrics-grid"></div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">DMS · 品类出货量</h2>
            <div class="panel-subtitle">各品类出货总量及分平台明细，含环比变化。点击品类可联动整页筛选。</div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll">
          <table class="shipment-table" id="shipment-category-table"></table>
        </div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">日趋势 · TT / 虾皮 / Lazada</h2>
            <div class="panel-subtitle">当月每日分渠道出货量趋势。</div>
          </div>
        </div>
        <div class="shipment-tri-chart">
          <div class="panel">
            <h3 style="font-size:16px;margin-bottom:10px;color:#ee4d2d;">TT销量日趋势</h3>
            <div class="chart-wrap-inner"><canvas id="chart-shipment-daily-tiktok"></canvas></div>
          </div>
          <div class="panel">
            <h3 style="font-size:16px;margin-bottom:10px;color:#2787e7;">虾皮销量日趋势</h3>
            <div class="chart-wrap-inner"><canvas id="chart-shipment-daily-shopee"></canvas></div>
          </div>
          <div class="panel">
            <h3 style="font-size:16px;margin-bottom:10px;color:#f5a623;">Lazada销量日趋势</h3>
            <div class="chart-wrap-inner"><canvas id="chart-shipment-daily-lazada"></canvas></div>
          </div>
        </div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title" id="shipment-detail-title">TT&amp;货架 · 月累计出货对比</h2>
            <div class="panel-subtitle" id="shipment-detail-subtitle">当月产品出货明细，含分渠道量及环比。</div>
          </div>
        </div>
        <div class="shipment-sku-filter">
          <label for="shipment-sku-search">搜索</label>
          <input id="shipment-sku-search" type="text" placeholder="输入SKU、品类或产品名...">
        </div>
        <div class="table-wrap meta-table-scroll">
          <table class="shipment-table" id="shipment-sku-table"></table>
        </div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">3渠道 · 月度出货趋势</h2>
            <div class="panel-subtitle">Tiktok / 虾皮 Shopee / Lazada 月度出货量趋势对比。</div>
          </div>
        </div>
        <div class="shipment-chart-wrap"><canvas id="chart-shipment-trend"></canvas></div>
      </section>

      <section class="formula-note">
        出货分析口径：数据来源于出货明细表，Platform 归一化为 Tiktok / Shopee / Lazada 三渠道；环比 = (当月 - 上月) / 上月 × 100%；当前月数据为月中实时累计，完整月数据需月末统计。点击品类可联动整页筛选，再次点击取消。
      </section>
    </main>
"""

# --------------------------------------------------------------------------- #
# JS
# --------------------------------------------------------------------------- #
JS = """
    // ===== Shipment Page Rendering =====
    const SHIPMENT_STATE = {
      category: null,      // active category filter (null = all)
      product: null,       // active product filter (sku), null = all
      dim: 'sku',          // detail table dimension: sku | category | name
      search: '',
    };

    function formatShipmentNumber(n) {
      const v = Number(n) || 0;
      return v.toLocaleString('en-US');
    }
    function formatShipmentDelta(delta) {
      if (delta === 0 || !isFinite(delta)) return '<span class="delta-flat">--</span>';
      const cls = delta > 0 ? 'delta-up' : 'delta-down';
      const arrow = delta > 0 ? '↑' : '↓';
      return `<span class="${cls}">${arrow} ${Math.abs(delta).toFixed(1)}%</span>`;
    }
    function shipmentBaseRows() {
      let rows = SHIPMENT_DATA.product_rows.slice();
      if (SHIPMENT_STATE.category) {
        rows = rows.filter(r => r.category === SHIPMENT_STATE.category);
      }
      if (SHIPMENT_STATE.product) {
        rows = rows.filter(r => r.sku === SHIPMENT_STATE.product);
      }
      return rows;
    }
    function shipmentSum(rows, key) {
      return rows.reduce((acc, r) => acc + (Number(r[key]) || 0), 0);
    }
    function renderShipmentFilterRow() {
      const row = document.getElementById('shipment-filter-row');
      const chips = [];
      if (SHIPMENT_STATE.category) {
        chips.push(`<span class="shipment-filter-chip">品类：${SHIPMENT_STATE.category}<button type="button" data-shipment-clear="category" title="清除品类筛选">×</button></span>`);
      }
      if (SHIPMENT_STATE.product) {
        const prod = SHIPMENT_DATA.product_rows.find(r => r.sku === SHIPMENT_STATE.product);
        chips.push(`<span class="shipment-filter-chip">产品：${prod ? (prod.name || prod.sku) : SHIPMENT_STATE.product}<button type="button" data-shipment-clear="product" title="清除产品筛选">×</button></span>`);
      }
      if (chips.length) {
        chips.push('<span class="shipment-filter-hint">已联动筛选整页数据 · 点击 × 或再次点击品类可恢复全部</span>');
      } else {
        chips.push('<span class="shipment-filter-hint">点击上方品类可联动筛选整页数据</span>');
      }
      row.innerHTML = chips.join('');
    }
    function renderShipmentMetrics() {
      const cards = SHIPMENT_DATA.channel_cards;
      const periodLabel = document.getElementById('shipment-period-label');
      periodLabel.textContent = `当月：${cards.current_ym}　对比上月：${cards.prev_ym}（环比变化）`;
      const grid = document.getElementById('shipment-metrics-grid');
      const colors = ['#ee4d2d', '#ee4d2d', '#2787e7', '#f5a623'];
      const rows = shipmentBaseRows();

      // Channel totals restricted to the current filter
      const filtered = {};
      filtered.total = shipmentSum(rows, 'total');
      filtered.tiktok = shipmentSum(rows, 'tiktok');
      filtered.shopee = shipmentSum(rows, 'shopee');
      filtered.lazada = shipmentSum(rows, 'lazada');

      // Previous-month baseline. When no filter is active we use the
      // authoritative month totals from the channel cards; when a category or
      // product filter is active we recompute from the filtered product set.
      const isFiltered = !!(SHIPMENT_STATE.category || SHIPMENT_STATE.product);
      const prevKey = { total: 'prev_total', tiktok: 'prev_tiktok', shopee: 'prev_shopee', lazada: 'prev_lazada' };

      grid.innerHTML = cards.cards.map((card, i) => {
        const key = card.key || (i === 0 ? 'total' : ['tiktok', 'shopee', 'lazada'][i - 1]);
        const color = colors[i] || '#44617f';
        const current = isFiltered ? filtered[key] : card.current;
        const prev = isFiltered ? shipmentSum(rows, prevKey[key]) : card.prev;
        const delta = prev ? ((current - prev) / prev * 100) : 0;
        const isActive = !isFiltered;
        return `
          <div class="shipment-metric-card ${isActive ? 'is-active' : 'is-dimmed'}">
            <div class="shipment-metric-label">${card.label}</div>
            <div class="shipment-metric-value" style="color:${color}">${formatShipmentNumber(current)}</div>
            <div class="shipment-metric-sub">
              上月 ${formatShipmentNumber(prev)}
              <span class="shipment-metric-delta">${formatShipmentDelta(Math.round(delta * 10) / 10)}</span>
            </div>
          </div>
        `;
      }).join('');
    }
    function renderShipmentCategoryTable() {
      const table = document.getElementById('shipment-category-table');
      const rows = SHIPMENT_DATA.category_table;
      const header = `
        <thead>
          <tr>
            <th>品类</th>
            <th>总量</th>
            <th>占比</th>
            <th>环比</th>
            <th>Tiktok</th>
            <th>TT占比</th>
            <th>TT环比</th>
            <th>Shopee</th>
            <th>SP占比</th>
            <th>SP环比</th>
            <th>Lazada</th>
            <th>LZ占比</th>
            <th>LZ环比</th>
          </tr>
        </thead>
      `;
      const body = rows.map(r => {
        const active = SHIPMENT_STATE.category === r.category;
        return `
        <tr${active ? ' style="background:rgba(39,135,231,.08);"' : ''}>
          <td><button type="button" class="shipment-cat-btn${active ? ' is-active' : ''}" data-shipment-category="${r.category}">${r.category}</button></td>
          <td style="font-weight:700;">${formatShipmentNumber(r.total)}</td>
          <td>${r.share}%</td>
          <td>${formatShipmentDelta(r.delta)}</td>
          <td>${formatShipmentNumber(r.tiktok)}</td>
          <td>${r.tiktok_share}%</td>
          <td>${formatShipmentDelta(r.tiktok_delta)}</td>
          <td>${formatShipmentNumber(r.shopee)}</td>
          <td>${r.shopee_share}%</td>
          <td>${formatShipmentDelta(r.shopee_delta)}</td>
          <td>${formatShipmentNumber(r.lazada)}</td>
          <td>${r.lazada_share}%</td>
          <td>${formatShipmentDelta(r.lazada_delta)}</td>
        </tr>
      `;
      }).join('');
      table.innerHTML = header + '<tbody>' + body + '</tbody>';
    }
    function renderShipmentTrendChart() {
      const data = SHIPMENT_DATA.monthly_trend;
      const labels = data.map(d => d.ym);
      const config = {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Tiktok',
              data: data.map(d => d.tiktok),
              borderColor: '#ee4d2d',
              backgroundColor: 'rgba(238,77,45,0.1)',
              borderWidth: 2.5,
              pointRadius: 4,
              pointHoverRadius: 6,
              tension: 0.35,
              fill: false,
            },
            {
              label: 'Shopee',
              data: data.map(d => d.shopee),
              borderColor: '#2787e7',
              backgroundColor: 'rgba(39,135,231,0.1)',
              borderWidth: 2.5,
              pointRadius: 4,
              pointHoverRadius: 6,
              tension: 0.35,
              fill: false,
            },
            {
              label: 'Lazada',
              data: data.map(d => d.lazada),
              borderColor: '#f5a623',
              backgroundColor: 'rgba(245,166,35,0.1)',
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 5,
              tension: 0.35,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              position: 'top',
              labels: { color: '#44617f', font: { size: 13, weight: '700' } },
            },
            tooltip: {
              callbacks: {
                label: function(ctx) {
                  return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString();
                },
              },
            },
          },
          scales: {
            x: {
              ticks: { color: '#817365', font: { size: 11 } },
              grid: { display: false },
            },
            y: {
              ticks: {
                color: '#817365',
                callback: function(v) { return v >= 1000 ? v.toLocaleString('en-US') : v; },
              },
              grid: { color: 'rgba(61,42,17,0.08)' },
            },
          },
        },
      };
      if (state.charts['chart-shipment-trend']) state.charts['chart-shipment-trend'].destroy();
      state.charts['chart-shipment-trend'] = new Chart(document.getElementById('chart-shipment-trend'), config);
    }
    function renderShipmentDailyCharts() {
      const daily = SHIPMENT_DATA.daily_trend;
      function makeConfig(label, data, color) {
        return {
          type: 'bar',
          data: {
            labels: data.map(d => d.day + '日'),
            datasets: [{
              label,
              data: data.map(d => d.qty),
              backgroundColor: color,
              borderRadius: 6,
              barPercentage: 0.6,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'top',
                labels: { color: '#44617f', font: { size: 12, weight: '700' } },
              },
              tooltip: {
                callbacks: {
                  label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString(); },
                },
              },
            },
            scales: {
              x: { ticks: { color: '#817365', font: { size: 11 } }, grid: { display: false } },
              y: {
                ticks: {
                  color: '#817365',
                  callback: function(v) { return v >= 1000 ? v.toLocaleString('en-US') : v; },
                },
                grid: { color: 'rgba(61,42,17,0.08)' },
              },
            },
          },
        };
      }
      const specs = [
        ['chart-shipment-daily-tiktok', 'Tiktok', daily.tiktok, 'rgba(238,77,45,0.7)'],
        ['chart-shipment-daily-shopee', 'Shopee', daily.shopee, 'rgba(39,135,231,0.7)'],
        ['chart-shipment-daily-lazada', 'Lazada', daily.lazada, 'rgba(245,166,35,0.75)'],
      ];
      specs.forEach(([canvasId, label, data, color]) => {
        if (state.charts[canvasId]) state.charts[canvasId].destroy();
        state.charts[canvasId] = new Chart(document.getElementById(canvasId), makeConfig(label, data, color));
      });
    }
    function shipmentGroupRows(rows, dim) {
      const groups = new Map();
      rows.forEach(r => {
        let key, label;
        if (dim === 'category') {
          key = r.category || '未分类';
          label = key;
        } else if (dim === 'name') {
          key = r.name || r.sku;
          label = key;
        } else {          key = r.sku;
          label = r.sku;
        }        if (!groups.has(key)) {
          groups.set(key, {
            key: key, label: label, sku: r.sku, category: r.category, name: r.name || '',
            total: 0, tiktok: 0, shopee: 0, lazada: 0,
            prev_total: 0, prev_tiktok: 0, prev_shopee: 0, prev_lazada: 0,
          });
        }
        const g = groups.get(key);
        g.total += r.total; g.tiktok += r.tiktok; g.shopee += r.shopee; g.lazada += r.lazada;
        g.prev_total += r.prev_total || 0;
        g.prev_tiktok += r.prev_tiktok || 0;
        g.prev_shopee += r.prev_shopee || 0;
        g.prev_lazada += r.prev_lazada || 0;
      });
      return Array.from(groups.values()).sort((a, b) => b.total - a.total);
    }
    function renderShipmentSkuTable() {
      const table = document.getElementById('shipment-sku-table');
      const dim = SHIPMENT_STATE.dim;
      const titleEl = document.getElementById('shipment-detail-title');
      const subEl = document.getElementById('shipment-detail-subtitle');
      const dimLabel = { sku: 'SKU货号', category: '品类', name: '产品名' }[dim];

      let rows = shipmentBaseRows();
      if (SHIPMENT_STATE.search) {
        const q = SHIPMENT_STATE.search.toLowerCase();
        rows = rows.filter(r =>
          (r.sku || '').toLowerCase().includes(q) ||
          (r.name || '').toLowerCase().includes(q) ||
          (r.category || '').toLowerCase().includes(q)
        );
      }
      const groups = shipmentGroupRows(rows, dim);

      titleEl.textContent = `出货明细 · 按${dimLabel}汇总`;
      subEl.textContent = `当月${dimLabel}维度出货量、分渠道明细及环比，共 ${groups.length} 条。点击行内产品可进一步联动筛选。`;

      let header, body;
      if (dim === 'sku') {
        header = `
          <thead>
            <tr>
              <th>SKU货号</th><th>产品名</th><th>品类</th><th>总量</th>
              <th>Tiktok</th><th>Shopee</th><th>Lazada</th><th>上月</th><th>环比</th>
            </tr>
          </thead>`;
        body = groups.map(g => {
          const active = SHIPMENT_STATE.product === g.sku;
          const delta = g.prev_total ? Math.round(((g.total - g.prev_total) / g.prev_total * 100) * 10) / 10 : 0;
          return `
          <tr${active ? ' style="background:rgba(39,135,231,.08);"' : ''}>
            <td style="font-weight:700;color:#2787e7;">${g.key}</td>
            <td style="text-align:left;"><button type="button" class="shipment-product-btn${active ? ' is-active' : ''}" data-shipment-product="${g.sku}">${g.name || g.label}</button></td>
            <td style="text-align:left;">${g.category}</td>
            <td style="font-weight:700;">${formatShipmentNumber(g.total)}</td>
            <td>${formatShipmentNumber(g.tiktok)}</td>
            <td>${formatShipmentNumber(g.shopee)}</td>
            <td>${formatShipmentNumber(g.lazada)}</td>
            <td>${formatShipmentNumber(g.prev_total)}</td>
            <td>${formatShipmentDelta(delta)}</td>
          </tr>`;
        }).join('');
      } else {
        header = `
          <thead>
            <tr>
              <th>${dimLabel}</th><th>品类</th><th>总量</th><th>占比</th>
              <th>Tiktok</th><th>Shopee</th><th>Lazada</th><th>上月</th><th>环比</th>
            </tr>
          </thead>`;
        const grandTotal = groups.reduce((a, g) => a + g.total, 0);
        body = groups.map(g => {
          const delta = g.prev_total ? Math.round(((g.total - g.prev_total) / g.prev_total * 100) * 10) / 10 : 0;
          const share = grandTotal ? (g.total / grandTotal * 100).toFixed(1) : '0.0';
          const isActive = dim === 'category' && SHIPMENT_STATE.category === g.key;
          const labelCell = dim === 'category'
            ? `<button type="button" class="shipment-cat-btn${isActive ? ' is-active' : ''}" data-shipment-category="${g.key}">${g.key}</button>`
            : `<button type="button" class="shipment-product-btn${SHIPMENT_STATE.product === g.sku ? ' is-active' : ''}" data-shipment-product="${g.sku}">${g.label}</button>`;
          return `
          <tr${isActive ? ' style="background:rgba(39,135,231,.08);"' : ''}>
            <td style="text-align:left;">${labelCell}</td>
            <td style="text-align:left;">${g.category}</td>
            <td style="font-weight:700;">${formatShipmentNumber(g.total)}</td>
            <td>${share}%</td>
            <td>${formatShipmentNumber(g.tiktok)}</td>
            <td>${formatShipmentNumber(g.shopee)}</td>
            <td>${formatShipmentNumber(g.lazada)}</td>
            <td>${formatShipmentNumber(g.prev_total)}</td>
            <td>${formatShipmentDelta(delta)}</td>
          </tr>`;
        }).join('');
      }
      table.innerHTML = header + '<tbody>' + body + '</tbody>';
    }
    function renderShipmentPage() {
      const dimRow = document.getElementById('shipment-dim-row');
      if (dimRow) dimRow.hidden = state.activePage !== 'shipment';
      renderShipmentFilterRow();
      renderShipmentMetrics();
      renderShipmentCategoryTable();
      renderShipmentTrendChart();
      renderShipmentDailyCharts();
      renderShipmentSkuTable();
    }
    function applyShipmentFilter() {
      renderShipmentFilterRow();
      renderShipmentMetrics();
      renderShipmentCategoryTable();
      renderShipmentDailyCharts();
      renderShipmentSkuTable();
    }
    // Shipment interaction handlers (category click / product click / dim switch / search)
    document.addEventListener('click', function(e) {
      const catBtn = e.target.closest('[data-shipment-category]');
      if (catBtn) {
        const cat = catBtn.getAttribute('data-shipment-category');
        SHIPMENT_STATE.category = (SHIPMENT_STATE.category === cat) ? null : cat;
        SHIPMENT_STATE.product = null;
        applyShipmentFilter();
        return;
      }
      const prodBtn = e.target.closest('[data-shipment-product]');
      if (prodBtn) {
        const sku = prodBtn.getAttribute('data-shipment-product');
        SHIPMENT_STATE.product = (SHIPMENT_STATE.product === sku) ? null : sku;
        applyShipmentFilter();
        return;
      }
      const clearBtn = e.target.closest('[data-shipment-clear]');
      if (clearBtn) {
        const what = clearBtn.getAttribute('data-shipment-clear');
        if (what === 'category') SHIPMENT_STATE.category = null;
        if (what === 'product') SHIPMENT_STATE.product = null;
        applyShipmentFilter();
        return;
      }
      const dimBtn = e.target.closest('#shipment-dim-switch-top button, #shipment-dim-switch button');
      if (dimBtn) {
        SHIPMENT_STATE.dim = dimBtn.getAttribute('data-dim');
        document.querySelectorAll('#shipment-dim-switch-top button, #shipment-dim-switch button').forEach(b => {
          b.classList.toggle('is-active', b.getAttribute('data-dim') === SHIPMENT_STATE.dim);
        });
        renderShipmentSkuTable();
        return;
      }
    });
    document.addEventListener('input', function(e) {
      if (e.target.id === 'shipment-sku-search') {
        SHIPMENT_STATE.search = e.target.value;
        renderShipmentSkuTable();
      }
    });
"""

# --------------------------------------------------------------------------- #
# Injection helpers
# --------------------------------------------------------------------------- #
def replace_block(text, start_marker, end_marker, new_block, label):
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"[!] start marker not found for {label}: {start_marker!r}")
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit(f"[!] end marker not found for {label}: {end_marker!r}")
    return text[:start] + new_block + text[end + len(end_marker):]


def main():
    index_text = INDEX.read_text(encoding="utf-8")
    data_text = DATA.read_text(encoding="utf-8")
    payload = json.dumps(json.loads(data_text), ensure_ascii=False, separators=(",", ":"))

    # ---- 1. CSS -------------------------------------------------------
    index_text = replace_block(
        index_text,
        "    /* ===== Shipment Page ===== */",
        "      .shipment-dual-chart { grid-template-columns: 1fr; }\n    }\n",
        CSS,
        "shipment CSS",
    )

    # ---- 2. HTML ------------------------------------------------------
    index_text = replace_block(
        index_text,
        '    <main class="dashboard-page" id="shipment-page" hidden>',
        "    </main>\n  </div>\n",
        HTML,
        "shipment HTML",
    )

    # ---- 3. JS payload -------------------------------------------------
    old_data_start = "    const SHIPMENT_DATA = "
    idx = index_text.find(old_data_start)
    if idx == -1:
        raise SystemExit("[!] SHIPMENT_DATA declaration not found")
    # find the terminating ";" of that statement
    semi = index_text.find(";\n", idx)
    index_text = (index_text[:idx]
                  + f"    const SHIPMENT_DATA = {payload};\n"
                  + index_text[semi + 2:])

    # ---- 4. JS logic ---------------------------------------------------
    js_start = "    // ===== Shipment Page Rendering ====="
    js_end = "    syncDateInputs();"
    index_text = replace_block(
        index_text, js_start, js_end, JS + "\n    syncDateInputs();", "shipment JS"
    )

    INDEX.write_text(index_text, encoding="utf-8")
    print(f"[OK] index.html updated ({len(index_text):,} chars)")


if __name__ == "__main__":
    main()
