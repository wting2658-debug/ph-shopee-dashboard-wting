#!/usr/bin/env python3
"""Canonical isolated subsidy page; synchronize through sync_build_script.py."""
from pathlib import Path

CSS = r"""
    /* ===== Subsidy Page ===== */
    #subsidy-page { color: #24364b; }
    #subsidy-page .subsidy-panel { background: #fff; border: 1px solid #dce5ee; border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 18px rgba(30,54,80,.035); }
    #subsidy-page .subsidy-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
    #subsidy-page h2 { margin: 0; font-size: 22px; font-weight: 800; color: #21374b; }
    #subsidy-page h2 em { color: #e6434a; font-style: normal; }
    #subsidy-page .subsidy-note { color: #697d91; font-size: 13px; line-height: 1.7; }
    #subsidy-page .subsidy-month-select { border: 1px solid #cdd9e5; padding: 8px 12px; border-radius: 8px; background: #fff; color: #273c51; font-size: 15px; }
    #subsidy-page .subsidy-summary { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)) minmax(230px,1.7fr); gap: 24px; align-items: center; margin-bottom: 24px; }
    #subsidy-page .subsidy-kpi { padding: 6px 4px; }
    #subsidy-page .subsidy-kpi-label { font-size: 14px; color: #596d82; margin-bottom: 8px; }
    #subsidy-page .subsidy-kpi-value { font-size: 31px; line-height: 1.2; font-weight: 800; color: #21374b; font-variant-numeric: tabular-nums; }
    #subsidy-page .subsidy-kpi-rate { color: #e4434c; margin-top: 6px; font-size: 15px; }
    #subsidy-page .subsidy-progress { background: #edf0f4; height: 10px; border-radius: 8px; margin-top: 14px; overflow: hidden; }
    #subsidy-page .subsidy-progress span { display: block; height: 100%; background: #ef5157; border-radius: 8px; }
    #subsidy-page .subsidy-target { font-size: 12px; color: #7b8b9c; text-align: right; margin-top: 6px; }
    #subsidy-page .subsidy-side-kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 22px; }
    #subsidy-page .subsidy-side-kpis span { font-size: 13px; color: #697d91; display: block; margin-bottom: 5px; }
    #subsidy-page .subsidy-side-kpis strong { font-size: 25px; font-weight: 700; color: #263b51; }
    #subsidy-page .subsidy-positive { color: #e4444d !important; }
    #subsidy-page .subsidy-negative { color: #179b72 !important; }
    #subsidy-page .subsidy-table-wrap { overflow: auto; border-radius: 9px; border: 1px solid #dde7f0; max-height: 600px; }
    #subsidy-page .subsidy-sales-table-wrap { max-height: 480px; }
    #subsidy-page .subsidy-table th { position: sticky; top: 0; z-index: 1; }
    #subsidy-page .subsidy-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 16px; font-variant-numeric: tabular-nums; }
    #subsidy-page .subsidy-table th, #subsidy-page .subsidy-table td { width: auto; font-size: 16px; line-height: 1.5; border-left: 0; overflow-wrap: normal; vertical-align: middle; }
    #subsidy-page .subsidy-table th { background: #378de5; color: #fff; padding: 14px 16px; font-size: 17px; font-weight: 700; white-space: nowrap; text-align: right; }
    #subsidy-page .subsidy-table td { padding: 13px 16px; border-bottom: 1px solid #e8edf3; white-space: nowrap; text-align: right; }
    #subsidy-page #subsidy-sales-table { min-width: 1120px; }
    #subsidy-page .subsidy-table tbody tr:nth-child(odd) { background: #f3f5f8; }
    #subsidy-page .subsidy-table tbody tr:hover { background: #edf4fb; }
    #subsidy-page .subsidy-table .subsidy-text { text-align: left; }
    #subsidy-page .subsidy-table .subsidy-selected td { background: #eaf3ff; }
    #subsidy-page .subsidy-bar { display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
    #subsidy-page .subsidy-bar > span:first-child { flex-shrink: 0; }
    #subsidy-page .subsidy-bar-track { width: 60px; height: 14px; background: #e7edf3; display: inline-block; flex-shrink: 0; }
    #subsidy-page .subsidy-bar-fill { height: 100%; display: block; }
    #subsidy-page .subsidy-four-charts { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 16px; }
    #subsidy-page .subsidy-chart-card { background: #fff; border: 1px solid #dce5ee; border-radius: 14px; padding: 18px 14px 12px; min-width: 0; }
    #subsidy-page .subsidy-chart-card h3 { font-size: 15px; font-weight: 700; margin: 0 0 8px; color: #24364b; }
    #subsidy-page .subsidy-chart-card .subsidy-chart-unit { color: #8392a3; font-size: 12px; margin-bottom: 12px; }
    #subsidy-page .subsidy-chart-wrap { height: 230px; position: relative; cursor: zoom-in; }
    #subsidy-page .subsidy-chart-wrap.chart-zoomed { position: fixed; inset: 6vh 6vw; height: 88vh; z-index: 100; padding: 22px; border: 1px solid #cdd9e5; border-radius: 18px; background: #fff; box-shadow: 0 24px 80px rgba(18,35,58,.28); cursor: zoom-out; }
    #subsidy-page .subsidy-chart-wrap canvas { width: 100% !important; height: 100% !important; }
    #subsidy-page .subsidy-legend { display: flex; flex-wrap: wrap; gap: 18px; color: #697d91; font-size: 13px; }
    #subsidy-page .subsidy-legend i { display: inline-block; width: 25px; border-top: 3px solid #f47a2a; vertical-align: middle; margin-right: 7px; }
    #subsidy-page .subsidy-legend i.dashed { border-color: #91a6c1; border-top-style: dashed; }
    #subsidy-page .subsidy-monthly-table-wrap { overflow: visible; max-height: none; }
    #subsidy-page #subsidy-monthly-table { min-width: 0; width: 100%; font-size: 13px; }
    #subsidy-page #subsidy-monthly-table th, #subsidy-page #subsidy-monthly-table td { font-size: 13px; padding: 10px 7px; white-space: normal; line-height: 1.35; overflow-wrap: anywhere; }
    #subsidy-page #subsidy-monthly-table th { font-size: 13px; padding: 11px 7px; }
    #subsidy-page #subsidy-monthly-table .subsidy-bar { gap: 5px; }
    #subsidy-page #subsidy-monthly-table .subsidy-bar-track { width: 34px; height: 12px; }
    #subsidy-page #subsidy-monthly-table .subsidy-partial { font-size: 11px; padding: 1px 3px; margin-left: 3px; }
    #subsidy-page #subsidy-monthly-table th { background: #4bb2dc; }
    #subsidy-page #subsidy-monthly-table th.subsidy-tt { background: #429cbb; }
    #subsidy-page #subsidy-monthly-table th.subsidy-sp { background: #e69739; }
    #subsidy-page #subsidy-monthly-table td.subsidy-tt { background: #edf7fb; }
    #subsidy-page #subsidy-monthly-table td.subsidy-sp { background: #fff7ea; }
    #subsidy-page .subsidy-monthly-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    #subsidy-page .subsidy-empty { padding: 18px; color: #8493a3; font-size: 14px; }
    #subsidy-page .subsidy-partial { display: inline-block; background: #fff2d9; color: #a26b16; border-radius: 5px; font-size: 13px; padding: 2px 5px; margin-left: 8px; }
    #subsidy-page .subsidy-source { margin-top: 14px; }
    #subsidy-page .subsidy-source a { color: #327b9c; }
    #subsidy-page .subsidy-month-select { cursor: pointer; }
    #subsidy-page .subsidy-rollup { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 20px; }
    #subsidy-page .subsidy-rollup-card { background: #fff; border: 1px solid #dce5ee; border-radius: 14px; padding: 18px 16px 14px; min-width: 0; }
    #subsidy-page .subsidy-rollup-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 4px; }
    #subsidy-page .subsidy-rollup-head h3 { font-size: 17px; font-weight: 800; margin: 0; color: #24364b; }
    #subsidy-page .subsidy-rollup-head .subsidy-rollup-scope { color: #8392a3; font-size: 12px; margin-top: 3px; }
    #subsidy-page .subsidy-rollup-kpis { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px 16px; margin: 10px 0 4px; }
    #subsidy-page .subsidy-rollup-kpi span { display: block; font-size: 12.5px; color: #6b7f94; margin-bottom: 3px; }
    #subsidy-page .subsidy-rollup-kpi strong { font-size: 21px; font-weight: 800; color: #21374b; font-variant-numeric: tabular-nums; }
    #subsidy-page .subsidy-rollup-kpi em { font-style: normal; display: block; font-size: 12.5px; margin-top: 2px; color: #7b8b9c; }
    #subsidy-page .subsidy-rollup-kpi em.subsidy-positive { color: #e4444d; }
    #subsidy-page .subsidy-rollup-kpi em.subsidy-negative { color: #179b72; }
    #subsidy-page .subsidy-rollup-chart { height: 300px; position: relative; cursor: zoom-in; margin-top: 10px; }
    #subsidy-page .subsidy-rollup-chart.chart-zoomed { position: fixed; inset: 6vh 6vw; height: 88vh; z-index: 100; padding: 22px; border: 1px solid #cdd9e5; border-radius: 18px; background: #fff; box-shadow: 0 24px 80px rgba(18,35,58,.28); cursor: zoom-out; }
    #subsidy-page .subsidy-rollup-chart canvas { width: 100% !important; height: 100% !important; }
    #subsidy-page .subsidy-rollup-note { font-size: 12.5px; color: #7b8b9c; line-height: 1.6; margin-top: 10px; }
    @media(max-width: 1200px) { #subsidy-page .subsidy-rollup { grid-template-columns: 1fr; } }
    @media(max-width: 580px) { #subsidy-page .subsidy-rollup-kpis { grid-template-columns: 1fr; } }
    @media(max-width: 1200px) { #subsidy-page .subsidy-four-charts { grid-template-columns: repeat(2,minmax(0,1fr)); } }
    @media(max-width: 850px) { #subsidy-page .subsidy-summary { grid-template-columns: repeat(3,minmax(0,1fr)); } #subsidy-page .subsidy-side-kpis { grid-column: 1/-1; grid-template-columns: repeat(4,minmax(0,1fr)); } #subsidy-page .subsidy-kpi-value { font-size: 26px; } #subsidy-page .subsidy-monthly-charts { grid-template-columns: 1fr; } }
    @media(max-width: 580px) { #subsidy-page .subsidy-panel { padding: 16px; } #subsidy-page .subsidy-four-charts { grid-template-columns: 1fr; } #subsidy-page .subsidy-summary { gap: 12px; } #subsidy-page .subsidy-kpi-value { font-size: 22px; } #subsidy-page .subsidy-side-kpis { grid-template-columns: 1fr 1fr; } }
    /* ===== End Subsidy Page ===== */
"""

HTML = r"""
    <!-- ===== Subsidy Page ===== -->
    <main class="dashboard-page" id="subsidy-page" hidden>
      <section class="subsidy-panel">
        <div class="subsidy-head">
          <h2>PH-SKINTIFIC · <em>销售概览</em></h2>
          <label class="subsidy-note">概览月份 <select id="subsidy-sales-month" class="subsidy-month-select" aria-label="销售概览月份"></select></label>
        </div>
        <div class="subsidy-summary" id="subsidy-sales-summary"></div>
        <div class="subsidy-note" style="margin-bottom:14px">沿用销售概览源表口径：累计达成、月目标、SOB 与环比；环比使用源表上月同期基数，包含源表退货退款调整，不混用补贴 GMV。概览月份独立选择，下表保留全部历史月份。</div>
        <div class="subsidy-table-wrap subsidy-sales-table-wrap"><table class="subsidy-table" id="subsidy-sales-table"></table></div>
        <div class="subsidy-note subsidy-source" id="subsidy-sales-source"></div>
      </section>
      <section class="subsidy-panel">
        <div class="subsidy-head">
          <div><h2>GMV &amp; 平台补贴率 · 日趋势</h2><div class="subsidy-note" id="subsidy-daily-range"></div></div>
          <div class="subsidy-legend"><span><i></i>查询期 · 实线</span><span><i class="dashed"></i>对比期 · 虚线</span></div>
        </div>
        <div class="subsidy-four-charts">
          <div class="subsidy-chart-card"><h3>Shopee · GMV</h3><div class="subsidy-chart-unit">人民币 · 元</div><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-sp-gmv"></canvas></div></div>
          <div class="subsidy-chart-card"><h3>Shopee · 平台补贴率</h3><div class="subsidy-chart-unit">平台补贴 / GMV</div><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-sp-rate"></canvas></div></div>
          <div class="subsidy-chart-card"><h3>TikTok · GMV</h3><div class="subsidy-chart-unit">人民币 · 元</div><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-tt-gmv"></canvas></div></div>
          <div class="subsidy-chart-card"><h3>TikTok · 平台补贴率</h3><div class="subsidy-chart-unit">平台补贴 / GMV</div><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-tt-rate"></canvas></div></div>
        </div>
        <div class="subsidy-note subsidy-source" id="subsidy-daily-source"></div>
      </section>
      <section class="subsidy-panel">
        <div class="subsidy-head">
          <div><h2>本月累计 · <em>GMV / 补贴 / 补贴率</em></h2><div class="subsidy-note" id="subsidy-rollup-range"></div></div>
          <div class="subsidy-legend"><span><i></i>本月逐日</span><span><i class="dashed"></i>上月同期</span></div>
        </div>
        <div class="subsidy-rollup" id="subsidy-rollup"></div>
        <div class="subsidy-note subsidy-source" id="subsidy-rollup-source"></div>
      </section>
      <section class="subsidy-panel">
        <div class="subsidy-head"><div><h2>月度补贴明细</h2><div class="subsidy-note">全渠道 = TT + Shopee + Lazada；货架 = Shopee + Lazada。独立展示全历史月份，不受顶部日期筛选影响；表格最新月份置顶。</div></div></div>
        <div class="subsidy-table-wrap subsidy-monthly-table-wrap"><table class="subsidy-table" id="subsidy-monthly-table"></table></div>
        <div class="subsidy-note subsidy-source" id="subsidy-monthly-source"></div>
      </section>
      <section class="subsidy-panel" id="subsidy-monthly-trends">
        <div class="subsidy-head"><div><h2>月度补贴趋势</h2><div class="subsidy-note">Shopee / TikTok 月度平台补贴率与补贴金额；独立展示全历史月份，不受顶部日期筛选影响，曲线按时间正序。</div></div></div>
        <div class="subsidy-monthly-charts">
          <div class="subsidy-chart-card"><h3>月度平台补贴率 · Shopee / TikTok</h3><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-monthly-rate"></canvas></div></div>
          <div class="subsidy-chart-card"><h3>月度补贴金额 · Shopee / TikTok</h3><div class="subsidy-chart-wrap" data-chart-wrap><canvas id="chart-subsidy-monthly-amount"></canvas></div></div>
        </div>
      </section>
    </main>
    <!-- ===== End Subsidy Page ===== -->
"""

JS = r"""
    // ===== Subsidy Page Rendering =====
    const SUBSIDY_DATA = __SUBSIDY_JSON__;
    const SUBSIDY_STATE = { salesMonth: SUBSIDY_DATA.coverage.latest_sales_month };
    const subsidyValid = value => value !== null && value !== undefined && Number.isFinite(value);
    const subsidyText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const subsidyNumber = (value, digits = 0) => subsidyValid(value) ? value.toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '—';
    const subsidyWan = value => subsidyValid(value) ? `${(value / 10000).toFixed(1)}万` : '—';
    const subsidyPercent = (value, digits = 2) => subsidyValid(value) ? `${(value * 100).toFixed(digits)}%` : '—';
    const subsidyRatio = (a,b) => subsidyValid(a) && subsidyValid(b) && b !== 0 ? a / b : null;
    const subsidySum = values => values.length && values.every(subsidyValid) ? values.reduce((a,b) => a + b, 0) : null;
    const subsidyDeltaClass = value => !subsidyValid(value) || value === 0 ? '' : value > 0 ? 'subsidy-positive' : 'subsidy-negative';
    function subsidyBar(value, maximum, color) {
      const width = subsidyValid(value) && maximum > 0 ? Math.max(0, Math.min(100, value / maximum * 100)) : 0;
      return `<div class="subsidy-bar"><span title="${subsidyNumber(value)} 元">${subsidyWan(value)}</span><span class="subsidy-bar-track"><span class="subsidy-bar-fill" style="width:${width}%;background:${color}"></span></span></div>`;
    }
    function subsidyMonthBadge(month) {
      return month === SUBSIDY_DATA.coverage.latest_month ? '<span class="subsidy-partial" title="月度源表最新累计月份，未提供独立截止日">最新</span>' : '';
    }
    function renderSubsidySales() {
      const rows = SUBSIDY_DATA.sales;
      const months = [...new Set(rows.map(r => r.month))];
      document.getElementById('subsidy-sales-month').innerHTML = months.map(month => `<option value="${month}" ${month === SUBSIDY_STATE.salesMonth ? 'selected' : ''}>${month}</option>`).join('');
      const selected = rows.filter(r => r.month === SUBSIDY_STATE.salesMonth);
      const tt = selected.find(r => r.platform === 'TT'), shelf = selected.find(r => r.platform === '货架');
      const total = subsidySum([tt?.actual, shelf?.actual]), target = subsidySum([tt?.target, shelf?.target]);
      const kpi = (label, actual, goal, rate) => `<div class="subsidy-kpi"><div class="subsidy-kpi-label">${label}</div><div class="subsidy-kpi-value" title="${subsidyNumber(actual)} 元">${subsidyWan(actual)}</div><div class="subsidy-kpi-rate">${subsidyPercent(rate,1)}</div><div class="subsidy-progress"><span style="width:${subsidyValid(rate) ? Math.max(0,Math.min(100,rate*100)) : 0}%"></span></div><div class="subsidy-target">目标 ${subsidyWan(goal)}</div></div>`;
      document.getElementById('subsidy-sales-summary').innerHTML = kpi('全渠道累计达成',total,target,subsidyRatio(total,target)) + kpi('TT 累计达成',tt?.actual,tt?.target,tt?.achievement) + kpi('货架累计达成',shelf?.actual,shelf?.target,shelf?.achievement) + `<div class="subsidy-side-kpis"><div><span>货架环比</span><strong class="${subsidyDeltaClass(shelf?.mom)}">${subsidyPercent(shelf?.mom)}</strong></div><div><span>货架 SOB</span><strong>${subsidyPercent(shelf?.share,1)}</strong></div><div><span>TT 环比</span><strong class="${subsidyDeltaClass(tt?.mom)}">${subsidyPercent(tt?.mom)}</strong></div><div><span>TT SOB</span><strong>${subsidyPercent(tt?.share,1)}</strong></div></div>`;
      const max = Math.max(1,...rows.map(r => r.actual ?? 0));
      document.getElementById('subsidy-sales-table').innerHTML = '<colgroup><col style="width:80px"><col style="width:120px"><col style="width:64px"><col style="width:150px"><col style="width:210px"><col style="width:132px"><col style="width:118px"><col style="width:146px"></colgroup><thead><tr><th class="subsidy-text">年</th><th class="subsidy-text">Platform</th><th>月</th><th>GMV目标</th><th>累计达成 · RMB</th><th>达成率</th><th>SOB</th><th>环比</th></tr></thead><tbody>' + rows.map(r => `<tr class="${r.month === SUBSIDY_STATE.salesMonth ? 'subsidy-selected' : ''}"><td class="subsidy-text">${r.year}</td><td class="subsidy-text">${r.platform === 'TT' ? 'TikTok' : '货架'}</td><td>${r.month_number}</td><td title="${subsidyNumber(r.target)} 元">${subsidyWan(r.target)}</td><td>${subsidyBar(r.actual,max,'#ef5b94')}</td><td>${subsidyPercent(r.achievement)}</td><td>${subsidyPercent(r.share)}</td><td class="${subsidyDeltaClass(r.mom)}" title="上月同期 ${subsidyNumber(r.previous)} 元">${subsidyPercent(r.mom)}</td></tr>`).join('') + '</tbody>';
      document.getElementById('subsidy-sales-source').innerHTML = `数据源：<a href="${subsidyText(SUBSIDY_DATA.sources.sales)}" target="_blank" rel="noopener">销售概览工作表</a> · 金额单位：人民币 · 最新月份 ${SUBSIDY_DATA.coverage.latest_sales_month}`;
    }
    function subsidyDates(start,end) {
      const out = [], current = new Date(start+'T00:00:00Z'), stop = new Date(end+'T00:00:00Z');
      while (current <= stop && out.length < 3660) { out.push(current.toISOString().slice(0,10)); current.setUTCDate(current.getUTCDate()+1); }
      return out;
    }
    function subsidyChartOptions(rate, datesBySet = null, dualAxis = false) {
      const dateOf = (datasetIndex, dataIndex) => {
        if (!datesBySet) return '';
        const set = datesBySet[datasetIndex];
        return set && set[dataIndex] ? set[dataIndex] : '';
      };
      return { responsive:true, maintainAspectRatio:false, animation:false, interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:!datesBySet,position:'bottom',labels:{color:'#526b84',boxWidth:18,font:{size:12},usePointStyle:true,pointStyle:'line'}},tooltip:{callbacks:{
          title: items => items.length ? (datesBySet ? '按区间第 '+(items[0].dataIndex+1)+' 天对齐' : items[0].label) : '',
          label: context => `${context.dataset.label}${datesBySet ? ' · '+dateOf(context.datasetIndex, context.dataIndex) : ''}：${rate ? subsidyPercent(context.parsed.y) : subsidyNumber(context.parsed.y,2)+' 元'}`
        }}}, scales:{x:{grid:{display:false},ticks:{color:'#73889e',maxTicksLimit:8,maxRotation:0,font:{size:11}}},y:{beginAtZero:true,position:'left',grid:{color:'#edf1f5'},ticks:{color:'#73889e',maxTicksLimit:6,font:{size:11},callback:value => rate ? `${(value*100).toFixed(0)}%` : value >= 10000 ? `${(value/10000).toFixed(1)}万` : subsidyNumber(value)}},
          ...(dualAxis ? {y1:{beginAtZero:true,position:'right',grid:{display:false},ticks:{color:'#b08a6a',maxTicksLimit:6,font:{size:11},callback:value => value >= 10000 ? `${(value/10000).toFixed(1)}万` : subsidyNumber(value)}}} : {})}};
    }
    function renderSubsidyDaily() {
      const currentDates = subsidyDates(state.start,state.end), previousDates = subsidyDates(state.compareStart,state.compareEnd);
      const length = Math.max(currentDates.length,previousDates.length);
      const byDate = new Map(SUBSIDY_DATA.daily.map(r => [r.date,r]));
      const aligned = Array.from({length}, (_,i) => i);
      const labels = aligned.map(i => currentDates[i]?.slice(5) || `第${i+1}天`);
      const specs = [['sp','gmv',false],['sp','rate',true],['tt','gmv',false],['tt','rate',true]];
      specs.forEach(([channel,metric,rate]) => {
        const field = `${channel}_${metric}`;
        const datasets = [[currentDates,'查询期','#f47a2a',[]],[previousDates,'对比期','#91a6c1',[7,5]]].map(([dates,label,color,dash]) => ({label,data:aligned.map(i => dates[i] ? (byDate.get(dates[i])?.[field] ?? null) : null),borderColor:color,backgroundColor:color,borderWidth:2.3,borderDash:dash,tension:.25,pointRadius:2.4,pointHoverRadius:5,pointHitRadius:12,spanGaps:false,fill:false}));
        upsertChart(`chart-subsidy-${channel}-${metric}`,{type:'line',data:{labels,datasets},options:subsidyChartOptions(rate,[currentDates,previousDates])});
      });
      const currentCount = currentDates.filter(date => byDate.has(date)).length, previousCount = previousDates.filter(date => byDate.has(date)).length;
      document.getElementById('subsidy-daily-range').textContent = `查询 ${state.start} → ${state.end}（${currentCount} 天有源数据） · 对比 ${state.compareStart} → ${state.compareEnd}（${previousCount} 天有源数据） · 严格使用顶部日期，按区间第 N 天对齐`;
      document.getElementById('subsidy-daily-source').innerHTML = `数据源：<a href="${subsidyText(SUBSIDY_DATA.sources.daily)}" target="_blank" rel="noopener">日 GMV 与补贴工作表</a> · 数据覆盖 ${SUBSIDY_DATA.coverage.daily_start} → ${SUBSIDY_DATA.coverage.daily_end}。未到数、空值与除零补贴率留空，不补 0、不连接缺失点；日趋势仅展示 Shopee 与 TikTok。注意：源表 2025-10 的 Shopee 整月金额集中在 10-01，其余日为源表 0 值，此为集中记账而非真实日销售分布。`;
    }
    function subsidyRollupDelta(current, previous) {
      if (!subsidyValid(current) || !subsidyValid(previous) || previous === 0) return null;
      return (current - previous) / Math.abs(previous);
    }
    function subsidyRollupKpi(label, value, previousValue, kind) {
      const delta = subsidyRollupDelta(value, previousValue);
      const shown = kind === 'rate' ? subsidyPercent(value) : subsidyNumber(value);
      const previousShown = kind === 'rate' ? subsidyPercent(previousValue) : subsidyNumber(previousValue);
      const deltaText = !subsidyValid(delta) ? '—' : `${delta >= 0 ? '↑' : '↓'} ${subsidyPercent(Math.abs(delta),1)}`;
      const compare = kind === 'rate' ? '上月同期' : '上月同期累计';
      return `<div class="subsidy-rollup-kpi"><span>${label}</span><strong title="${kind === 'rate' ? '' : subsidyNumber(value) + ' 元'}">${shown}</strong><em class="${subsidyDeltaClass(delta)}">${deltaText}</em><em>${compare} ${previousShown}</em></div>`;
    }
    function renderSubsidyRollup() {
      const rollup = SUBSIDY_DATA.monthly_rollup || [];
      const latest = rollup[rollup.length - 1];
      const container = document.getElementById('subsidy-rollup');
      if (!latest) { container.innerHTML = '<div class="subsidy-empty">暂无月度累计数据。</div>'; return; }
      const byDate = new Map(SUBSIDY_DATA.daily.map(r => [r.date,r]));
      const monthDays = [];
      for (let day = 1; day <= 31; day++) {
        const candidate = `${latest.month}-${String(day).padStart(2,'0')}`;
        if (byDate.has(candidate)) monthDays.push({day, date: candidate});
      }
      const previousMonth = latest.previous_month;
      const previousDays = monthDays.length;
      const previousPoints = [];
      for (let day = 1; day <= previousDays; day++) {
        const candidate = previousMonth ? `${previousMonth}-${String(day).padStart(2,'0')}` : '';
        const record = candidate ? byDate.get(candidate) : null;
        previousPoints.push({day, date: candidate, record});
      }
      const labels = monthDays.map(item => `${Number(latest.month.slice(5))}/${item.day}`);
      const channelSpec = [
        {key:'tt', name:'TikTok', scope:'旗舰店', gmvColor:'#2f7de1', subsidyColor:'#f47a2a', gmvLabel:'tiktok本月累计', subsidyLabel:'TT-补贴'},
        {key:'sp', name:'Shopee', scope:'旗舰店+店群', gmvColor:'#6a8fe8', subsidyColor:'#f0a05a', gmvLabel:'Shopee本月累计', subsidyLabel:'包含的平台补贴金额'}
      ];
      container.innerHTML = channelSpec.map(spec => {
        const gmvData = monthDays.map(item => byDate.get(item.date)?.[`${spec.key}_gmv`] ?? null);
        const subsidyData = monthDays.map(item => byDate.get(item.date)?.[`${spec.key}_subsidy`] ?? null);
        const previousGmv = previousPoints.map(item => item.record?.[`${spec.key}_gmv`] ?? null);
        const previousSubsidy = previousPoints.map(item => item.record?.[`${spec.key}_subsidy`] ?? null);
        const kpis = subsidyRollupKpi(spec.gmvLabel, latest[`${spec.key}_gmv`], latest[`previous_same_${spec.key}_gmv`], 'amount')
          + subsidyRollupKpi(spec.subsidyLabel, latest[`${spec.key}_subsidy`], latest[`previous_same_${spec.key}_subsidy`], 'amount')
          + subsidyRollupKpi('本月补贴率', latest[`${spec.key}_rate`], latest[`previous_same_${spec.key}_rate`], 'rate');
        return `<div class="subsidy-rollup-card">
          <div class="subsidy-rollup-head"><div><h3>${spec.name}渠道<span class="subsidy-rollup-scope">（${spec.scope}）</span></h3><div class="subsidy-rollup-scope">本月 ${latest.start} → ${latest.end}（已到 ${latest.days} 天） · 上月 ${previousMonth || '—'} 全月 ${latest.previous_days} 天</div></div></div>
          <div class="subsidy-rollup-kpis">${kpis}</div>
          <div class="subsidy-rollup-chart" data-chart-wrap><canvas id="chart-subsidy-rollup-${spec.key}"></canvas></div>
          <div class="subsidy-rollup-note">实线为本月逐日 GMV 与补贴，虚线为上月同期逐日；上方指标为本月累计与上月同期累计对比，补贴率 = 累计补贴 ÷ 累计 GMV。</div>
        </div>`;
      }).join('');
      channelSpec.forEach(spec => {
        const monthDaysData = monthDays.map(item => byDate.get(item.date)?.[`${spec.key}_gmv`] ?? null);
        const subsidySeries = monthDays.map(item => byDate.get(item.date)?.[`${spec.key}_subsidy`] ?? null);
        const previousGmv = previousPoints.map(item => item.record?.[`${spec.key}_gmv`] ?? null);
        const previousSubsidy = previousPoints.map(item => item.record?.[`${spec.key}_subsidy`] ?? null);
        const datasets = [
          {label:'本月 GMV',data:monthDaysData,borderColor:spec.gmvColor,backgroundColor:spec.gmvColor,borderWidth:2.3,tension:.25,pointRadius:2.6,pointHoverRadius:5.5,pointHitRadius:12,spanGaps:false,fill:false,yAxisID:'y'},
          {label:'上月 GMV',data:previousGmv,borderColor:'#9db4d4',backgroundColor:'#9db4d4',borderWidth:2,borderDash:[6,4],tension:.25,pointRadius:2.2,pointHoverRadius:5,pointHitRadius:12,spanGaps:false,fill:false,yAxisID:'y'},
          {label:'本月补贴',data:subsidySeries,borderColor:spec.subsidyColor,backgroundColor:spec.subsidyColor,borderWidth:2.3,tension:.25,pointRadius:2.6,pointHoverRadius:5.5,pointHitRadius:12,spanGaps:false,fill:false,yAxisID:'y1'},
          {label:'上月补贴',data:previousSubsidy,borderColor:'#f3c9a4',backgroundColor:'#f3c9a4',borderWidth:2,borderDash:[6,4],tension:.25,pointRadius:2.2,pointHoverRadius:5,pointHitRadius:12,spanGaps:false,fill:false,yAxisID:'y1'}
        ];
        const dateSets = [monthDays.map(i=>i.date),previousPoints.map(i=>i.date||''),monthDays.map(i=>i.date),previousPoints.map(i=>i.date||'')];
        upsertChart(`chart-subsidy-rollup-${spec.key}`,{type:'line',data:{labels,datasets},options:subsidyChartOptions(false,dateSets,true)});
      });
      document.getElementById('subsidy-rollup-range').textContent = `本月 ${latest.start} → ${latest.end}（已到 ${latest.days} 天，按日更新） · 对比上月 ${previousMonth || '—'} 同期间逐日与上月全月累计 · 环比以「本月累计 vs 上月同期累计」计算`;
      document.getElementById('subsidy-rollup-source').innerHTML = `数据源：<a href="${subsidyText(SUBSIDY_DATA.sources.daily)}" target="_blank" rel="noopener">日 GMV 与补贴工作表</a> · 金额单位：人民币 · 本月累计 ${subsidyNumber(latest.tt_gmv + latest.sp_gmv)} 元（TT + Shopee）；上月全月累计 ${subsidyNumber(latest.previous_tt_gmv + latest.previous_sp_gmv)} 元。补贴率按「累计补贴 ÷ 累计 GMV」计算，不对日补贴率取平均；本月未满月，累计值会随每日刷新增长，环比为进行时对比。`;
    }
    function renderSubsidyMonthly() {      const rows = SUBSIDY_DATA.monthly, labels = rows.map(r => r.month);
      const channelSets = (metric) => [['sp','Shopee','#f47a2a'],['tt','TikTok','#2989ae']].map(([key,label,color]) => ({label,data:rows.map(r => r[`${key}_${metric}`]),borderColor:color,backgroundColor:color,borderWidth:2.3,tension:.25,pointRadius:3,pointHoverRadius:6,spanGaps:false,fill:false}));
      upsertChart('chart-subsidy-monthly-rate',{type:'line',data:{labels,datasets:channelSets('rate')},options:subsidyChartOptions(true)});
      upsertChart('chart-subsidy-monthly-amount',{type:'line',data:{labels,datasets:channelSets('subsidy')},options:subsidyChartOptions(false)});
      const totalMax = Math.max(1,...rows.map(r => r.total ?? 0)), shelfMax = Math.max(1,...rows.map(r => r.shelf ?? 0));
      const amount = value => `<td title="${subsidyNumber(value)} 元">${subsidyWan(value)}</td>`;
      const channelAmount = (value,cl) => `<td class="${cl}" title="${subsidyNumber(value)} 元">${subsidyWan(value)}</td>`;
      document.getElementById('subsidy-monthly-table').innerHTML = '<colgroup><col style="width:6%"><col style="width:8%"><col style="width:4%"><col style="width:4%"><col style="width:11%"><col style="width:8%"><col style="width:7%"><col style="width:7%"><col style="width:11%"><col style="width:7%"><col style="width:8%"><col style="width:7%"><col style="width:7%"><col style="width:8%"></colgroup><thead><tr><th class="subsidy-text">Country</th><th class="subsidy-text">Brand</th><th>年</th><th>月</th><th>全渠道</th><th class="subsidy-tt">TT-GMV</th><th class="subsidy-tt">TT-补贴</th><th class="subsidy-tt">TT补贴占比</th><th>货架合计</th><th>货架占比</th><th class="subsidy-sp">① SP-GMV</th><th class="subsidy-sp">SP-补贴</th><th class="subsidy-sp">SP补贴占比</th><th>② LZD-GMV</th></tr></thead><tbody>' + [...rows].reverse().map(r => `<tr><td class="subsidy-text">${subsidyText(r.country)}</td><td class="subsidy-text">${subsidyText(r.brand)}</td><td>${r.year}</td><td>${r.month_number}${subsidyMonthBadge(r.month)}</td><td>${subsidyBar(r.total,totalMax,'#4bb2dc')}</td>${channelAmount(r.tt_gmv,'subsidy-tt')}${channelAmount(r.tt_subsidy,'subsidy-tt')}<td class="subsidy-tt">${subsidyPercent(r.tt_rate)}</td><td>${subsidyBar(r.shelf,shelfMax,'#ee9731')}</td><td>${subsidyPercent(r.shelf_share)}</td>${channelAmount(r.sp_gmv,'subsidy-sp')}${channelAmount(r.sp_subsidy,'subsidy-sp')}<td class="subsidy-sp">${subsidyPercent(r.sp_rate)}</td>${amount(r.lz_gmv)}</tr>`).join('') + '</tbody>';
      document.getElementById('subsidy-monthly-source').innerHTML = `数据源：<a href="${subsidyText(SUBSIDY_DATA.sources.monthly)}" target="_blank" rel="noopener">月度补贴工作表</a> · 金额单位：人民币，按截图以“万”展示，悬停查看完整元数；最新累计月份 ${SUBSIDY_DATA.coverage.latest_month}，月度源未提供独立截止日，不据日源日期推定已完月。月度曲线按时间正序、表格按月份倒序；保留 Lazada GMV，不展示 Lazada 补贴。`;
    }
    function renderSubsidyPage() { renderSubsidySales(); renderSubsidyDaily(); renderSubsidyRollup(); renderSubsidyMonthly(); }
    document.getElementById('subsidy-sales-month').addEventListener('change', event => { SUBSIDY_STATE.salesMonth = event.target.value; renderSubsidySales(); });
    if (location.hash === '#subsidy') state.activePage = 'subsidy';
    // ===== End Subsidy Page Rendering =====
"""


def _block(text, start_marker, end_marker, block, insert_before):
    if start_marker in text:
        start = text.index(start_marker)
        end = text.index(end_marker, start) + len(end_marker)
        return text[:start] + block.strip('\n') + text[end:]
    position = text.index(insert_before)
    return text[:position] + block.strip('\n') + '\n' + text[position:]


def update_template(text):
    text = _block(text, '    /* ===== Subsidy Page ===== */', '    /* ===== End Subsidy Page ===== */', CSS, '    /* ===== Shipment Page ===== */')
    text = _block(text, '    <!-- ===== Subsidy Page ===== -->', '    <!-- ===== End Subsidy Page ===== -->', HTML, '\n  <script>')
    text = _block(text, '    // ===== Subsidy Page Rendering =====', '    // ===== End Subsidy Page Rendering =====', JS, '    // ===== Shipment Page Rendering =====')
    nav_old = '''        <button class="dashboard-tab active" type="button" data-dashboard-page="store">店铺分析</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="meta">站外投放</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="onsite">站内投放</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="shipment">出货分析</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="subsidy">补贴&amp;趋势</button>'''
    nav_new = '''        <button class="dashboard-tab" type="button" data-dashboard-page="subsidy">渠道补贴&amp;趋势</button>
        <button class="dashboard-tab active" type="button" data-dashboard-page="store">店铺分析</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="meta">站外投放</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="onsite">站内投放</button>
        <button class="dashboard-tab" type="button" data-dashboard-page="shipment">出货分析</button>'''
    if nav_old in text:
        text = text.replace(nav_old, nav_new, 1)
    elif nav_new not in text:
        raise ValueError('Expected dashboard navigation sequence was not found')
    hidden_line = "      document.getElementById('shipment-page').hidden = state.activePage !== 'shipment';"
    if "document.getElementById('subsidy-page').hidden" not in text:
        text = text.replace(hidden_line, hidden_line + "\n      document.getElementById('subsidy-page').hidden = state.activePage !== 'subsidy';", 1)
    branch = "      if (state.activePage === 'shipment') {\n        renderShipmentPage();\n        return;\n      }"
    if "state.activePage === 'subsidy'" not in text:
        text = text.replace(branch, branch + "\n      if (state.activePage === 'subsidy') {\n        renderSubsidyPage();\n        return;\n      }", 1)
    if text.count('id="subsidy-page"') != 1 or text.count('data-dashboard-page="subsidy"') != 1:
        raise ValueError('Subsidy page registration failed')
    return text


if __name__ == '__main__':
    path = Path(__file__).resolve().parent / 'build_flagship_onsite_page1.py'
    original = path.read_text(encoding='utf-8')
    updated = update_template(original)
    if updated != original:
        path.write_text(updated, encoding='utf-8')
