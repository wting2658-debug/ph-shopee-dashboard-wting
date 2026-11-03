#!/usr/bin/env python3
"""
Sync shipment page changes into build_flagship_onsite_page1.py
so the auto-refresh pipeline preserves the new shipment tab.
"""
import json

BUILD_FILE = "build_flagship_onsite_page1.py"
DATA_FILE = "shipment_data.json"

with open(DATA_FILE, "r", encoding="utf-8") as f:
    shipment_data = json.load(f)
shipment_data_json = json.dumps(shipment_data, ensure_ascii=False)

with open(BUILD_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add shipment Tab button
old_tabs = '        <button class="dashboard-tab" type="button" data-dashboard-page="onsite">站内投放</button>\n      </div>'
new_tabs = '        <button class="dashboard-tab" type="button" data-dashboard-page="onsite">站内投放</button>\n        <button class="dashboard-tab" type="button" data-dashboard-page="shipment">出货分析</button>\n      </div>'
content = content.replace(old_tabs, new_tabs, 1)

# 2. Add CSS before </style>
shipment_css = """
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
      padding: 10px 12px;
      text-align: right;
      border-bottom: 1px solid var(--line);
    }
    .shipment-table th {
      font-weight: 700;
      color: #44617f;
      background: rgba(248,250,252,0.8);
      font-size: 13px;
      white-space: nowrap;
    }
    .shipment-table td:first-child,
    .shipment-table th:first-child {
      text-align: left;
    }
    .shipment-table tbody tr:hover {
      background: rgba(238,77,45,0.03);
    }
    .shipment-chart-wrap {
      position: relative;
      height: 340px;
    }
    .shipment-dual-chart {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }
    .shipment-dual-chart .panel {
      padding: 16px;
    }
    .shipment-dual-chart .chart-wrap-inner {
      position: relative;
      height: 280px;
    }
    .shipment-sku-filter {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .shipment-sku-filter input {
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 14px;
      width: 220px;
    }
    .shipment-sku-filter label {
      font-size: 13px;
      font-weight: 700;
      color: #44617f;
      white-space: nowrap;
    }
    @media (max-width: 860px) {
      .shipment-metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .shipment-dual-chart { grid-template-columns: 1fr; }
    }
"""
content = content.replace("  </style>", shipment_css + "\n  </style>", 1)

# 3. Add shipment-page HTML after onsite-page </main>
old_onsite_end = """      <section class="formula-note">
        站内投放口径：订单量 = 站内广告 Order；广告 GMV 占比 = Ads GMV / 店铺 GMV；ROI = Ads GMV / Ads Spend；CPC = Ads Spend / Clicks；CTR = Clicks / Impression；CVR = Order / Clicks；CPA = Ads Spend / Order。
      </section>
    </main>
  </div>"""

shipment_page_html = """      <section class="formula-note">
        站内投放口径：订单量 = 站内广告 Order；广告 GMV 占比 = Ads GMV / 店铺 GMV；ROI = Ads GMV / Ads Spend；CPC = Ads Spend / Clicks；CTR = Clicks / Impression；CVR = Order / Clicks；CPA = Ads Spend / Order。
      </section>
    </main>

    <main class="dashboard-page" id="shipment-page" hidden>
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">渠道总出货指标</h2>
            <div class="panel-subtitle" id="shipment-period-label"></div>
          </div>
        </div>
        <div class="shipment-metrics-grid" id="shipment-metrics-grid"></div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">DMS · 品类出货量</h2>
            <div class="panel-subtitle">各品类出货总量及分平台明细，含环比变化。</div>
          </div>
        </div>
        <div class="table-wrap meta-table-scroll">
          <table class="shipment-table" id="shipment-category-table"></table>
        </div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">TT销量 &amp; 货架出货趋势</h2>
            <div class="panel-subtitle">Tiktok 与 Shopee 月度出货量趋势对比。</div>
          </div>
        </div>
        <div class="shipment-chart-wrap"><canvas id="chart-shipment-trend"></canvas></div>
      </section>

      <section class="panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">日趋势 · 货架销量 / TT销量</h2>
            <div class="panel-subtitle">当月每日分平台出货量趋势。</div>
          </div>
        </div>
        <div class="shipment-dual-chart">
          <div class="panel">
            <h3 style="font-size:16px;margin-bottom:10px;color:#44617f;">货架销量日趋势</h3>
            <div class="chart-wrap-inner"><canvas id="chart-shipment-daily-shopee"></canvas></div>
          </div>
          <div class="panel">
            <h3 style="font-size:16px;margin-bottom:10px;color:#44617f;">TT销量日趋势</h3>
            <div class="chart-wrap-inner"><canvas id="chart-shipment-daily-tiktok"></canvas></div>
          </div>
        </div>
      </section>

      <section class="panel table-panel" style="margin-top: 18px;">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">TT&amp;货架 · 月累计出货对比</h2>
            <div class="panel-subtitle">当月Top50 SKU出货明细，含分平台量及环比。</div>
          </div>
        </div>
        <div class="shipment-sku-filter">
          <label for="shipment-sku-search">筛选SKU</label>
          <input id="shipment-sku-search" type="text" placeholder="输入SKU或产品名...">
        </div>
        <div class="table-wrap meta-table-scroll">
          <table class="shipment-table" id="shipment-sku-table"></table>
        </div>
      </section>

      <section class="formula-note">
        出货分析口径：数据来源于出货明细表，Platform 归一化为 Tiktok / Shopee / Lazada 三渠道；环比 = (当月 - 上月) / 上月 × 100%；当前月数据为月中实时累计，完整月数据需月末统计。
      </section>
    </main>
  </div>"""
content = content.replace(old_onsite_end, shipment_page_html, 1)

# 4. Add SHIPMENT_DATA constant and update renderAll
data_line = f'    const SHIPMENT_DATA = {shipment_data_json};'
content = content.replace('    const REFRESH_ENDPOINT = \'/refresh-data\';', data_line + '\n    const REFRESH_ENDPOINT = \'/refresh-data\';', 1)

# 5. Update renderAll
old_render = """    function renderAll() {
      document.getElementById('store-page').hidden = state.activePage !== 'store';
      document.getElementById('meta-page').hidden = state.activePage !== 'meta';
      document.getElementById('onsite-page').hidden = state.activePage !== 'onsite';"""
new_render = """    function renderAll() {
      document.getElementById('store-page').hidden = state.activePage !== 'store';
      document.getElementById('meta-page').hidden = state.activePage !== 'meta';
      document.getElementById('onsite-page').hidden = state.activePage !== 'onsite';
      document.getElementById('shipment-page').hidden = state.activePage !== 'shipment';"""
content = content.replace(old_render, new_render, 1)

old_onsite_render = """      if (state.activePage === 'onsite') {
        renderOnsitePage();
        return;
      }"""
new_onsite_render = """      if (state.activePage === 'onsite') {
        renderOnsitePage();
        return;
      }
      if (state.activePage === 'shipment') {
        renderShipmentPage();
        return;
      }"""
content = content.replace(old_onsite_render, new_onsite_render, 1)

# 6. Add shipment JS functions before syncDateInputs
shipment_js = """
    // ===== Shipment Page Rendering =====
    function formatShipmentNumber(n) {
      if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
      if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
      return String(n);
    }
    function formatShipmentDelta(delta) {
      if (delta === 0 || !isFinite(delta)) return '<span class="delta-flat">--</span>';
      const cls = delta > 0 ? 'delta-up' : 'delta-down';
      const arrow = delta > 0 ? '↑' : '↓';
      return `<span class="${cls}">${arrow} ${Math.abs(delta).toFixed(1)}%</span>`;
    }
    function renderShipmentMetrics() {
      const cards = SHIPMENT_DATA.channel_cards;
      const periodLabel = document.getElementById('shipment-period-label');
      const currYM = cards.current_ym;
      const prevYM = cards.prev_ym;
      periodLabel.textContent = `当月：${currYM}　对比上月：${prevYM}（环比变化）`;
      const grid = document.getElementById('shipment-metrics-grid');
      const colors = ['#ee4d2d', '#2787e7', '#f5a623', '#15966a'];
      grid.innerHTML = cards.cards.map((card, i) => {
        const color = colors[i] || '#44617f';
        return `
          <div class="shipment-metric-card">
            <div class="shipment-metric-label">${card.label}</div>
            <div class="shipment-metric-value" style="color:${color}">${formatShipmentNumber(card.current)}</div>
            <div class="shipment-metric-sub">
              上月 ${formatShipmentNumber(card.prev)}
              <span class="shipment-metric-delta">${formatShipmentDelta(card.delta)}</span>
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
      const body = rows.map(r => `
        <tr>
          <td style="font-weight:700;">${r.category}</td>
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
      `).join('');
      table.innerHTML = header + '<tbody>' + body + '</tbody>';
    }
    function renderShipmentTrendChart() {
      const data = SHIPMENT_DATA.monthly_trend;
      const labels = data.map(d => d.ym);
      const tiktokData = data.map(d => d.tiktok);
      const shopeeData = data.map(d => d.shopee);
      const lazadaData = data.map(d => d.lazada);
      const config = {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Tiktok',
              data: tiktokData,
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
              data: shopeeData,
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
              data: lazadaData,
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
                callback: function(v) { return v >= 10000 ? Math.round(v/10000)+'w' : v >= 1000 ? (v/1000).toFixed(0)+'k' : v; },
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
                  callback: function(v) { return v >= 1000 ? (v/1000).toFixed(1)+'k' : v; },
                },
                grid: { color: 'rgba(61,42,17,0.08)' },
              },
            },
          },
        };
      }
      if (state.charts['chart-shipment-daily-shopee']) state.charts['chart-shipment-daily-shopee'].destroy();
      state.charts['chart-shipment-daily-shopee'] = new Chart(
        document.getElementById('chart-shipment-daily-shopee'),
        makeConfig('Shopee', daily.shopee, 'rgba(39,135,231,0.7)')
      );
      if (state.charts['chart-shipment-daily-tiktok']) state.charts['chart-shipment-daily-tiktok'].destroy();
      state.charts['chart-shipment-daily-tiktok'] = new Chart(
        document.getElementById('chart-shipment-daily-tiktok'),
        makeConfig('Tiktok', daily.tiktok, 'rgba(238,77,45,0.7)')
      );
    }
    function renderShipmentSkuTable(filterText) {
      const table = document.getElementById('shipment-sku-table');
      let rows = SHIPMENT_DATA.sku_table;
      if (filterText && filterText.trim()) {
        const q = filterText.trim().toLowerCase();
        rows = rows.filter(r =>
          r.sku.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)
        );
      }
      const header = `
        <thead>
          <tr>
            <th>SKU</th>
            <th>产品名</th>
            <th>总量</th>
            <th>Tiktok</th>
            <th>Shopee</th>
            <th>Lazada</th>
            <th>上月</th>
            <th>环比</th>
          </tr>
        </thead>
      `;
      const body = rows.map(r => `
        <tr>
          <td style="font-weight:700;color:#2787e7;">${r.sku}</td>
          <td style="text-align:left;">${r.name}</td>
          <td style="font-weight:700;">${formatShipmentNumber(r.total)}</td>
          <td>${formatShipmentNumber(r.tiktok)}</td>
          <td>${formatShipmentNumber(r.shopee)}</td>
          <td>${formatShipmentNumber(r.lazada)}</td>
          <td>${formatShipmentNumber(r.prev_total)}</td>
          <td>${formatShipmentDelta(r.delta)}</td>
        </tr>
      `).join('');
      table.innerHTML = header + '<tbody>' + body + '</tbody>';
    }
    function renderShipmentPage() {
      renderShipmentMetrics();
      renderShipmentCategoryTable();
      renderShipmentTrendChart();
      renderShipmentDailyCharts();
      renderShipmentSkuTable('');
    }
    document.addEventListener('input', function(e) {
      if (e.target.id === 'shipment-sku-search') {
        renderShipmentSkuTable(e.target.value);
      }
    });
"""
content = content.replace('    syncDateInputs();\n    renderFilters();\n    renderAll();\n  </script>', shipment_js + '\n    syncDateInputs();\n    renderFilters();\n    renderAll();\n  </script>', 1)

with open(BUILD_FILE, "w", encoding="utf-8") as f:
    f.write(content)

print("Build script synced successfully!")
print(f"File size: {len(content)} bytes")
