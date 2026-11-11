// Livestream rendering shares only the existing date state and chart helper.
const LIVE_SHOP = new Map(LIVE_DATA.daily.map(row => [row.date, row]));
const LIVE_DAYS = new Map();
for (const session of LIVE_DATA.sessions) {
  if (!LIVE_DAYS.has(session.date)) LIVE_DAYS.set(session.date, []);
  LIVE_DAYS.get(session.date).push(session);
}
const LIVE_STATE = { date: null, compareMode: 'month' };
const LIVE_DETAIL_START = [LIVE_DATA.coverage.shop_start,LIVE_DATA.coverage.sessions_start].sort()[0];
const LIVE_DETAIL_END = [LIVE_DATA.coverage.shop_end,LIVE_DATA.coverage.sessions_end].sort().at(-1);
const liveEscape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const liveNumber = (value, decimals = 0) => value == null || !Number.isFinite(value) ? '—' : Number(value).toLocaleString('zh-CN', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
const liveMoney = value => value == null ? '—' : `¥${liveNumber(value, 2)}`;
const liveRate = value => value == null ? '—' : `${liveNumber(value * 100, 2)}%`;
const liveRatio = (numerator, denominator) => numerator == null || denominator == null || denominator === 0 ? null : numerator / denominator;

function liveDates(start, end) {
  const result = [];
  const day = new Date(`${start}T00:00:00Z`), last = new Date(`${end}T00:00:00Z`);
  if (!Number.isFinite(+day) || !Number.isFinite(+last)) return result;
  while (day <= last) { result.push(day.toISOString().slice(0, 10)); day.setUTCDate(day.getUTCDate() + 1); }
  return result;
}

function liveDay(date) {
  const rows = LIVE_DAYS.get(date) || [];
  const inSessionCoverage = date >= LIVE_DATA.coverage.sessions_start && date <= LIVE_DATA.coverage.sessions_end;
  const totals = {date, shop_gmv: LIVE_SHOP.get(date)?.shop_gmv ?? null, gmv: null, hours: null, likes: null, buyers: null, sessions: rows.length};
  if (inSessionCoverage) {
    for (const key of ['gmv','hours','likes','buyers']) totals[key] = rows.reduce((sum, row) => sum + row[key], 0);
  }
  totals.share = liveRatio(totals.gmv, totals.shop_gmv);
  return totals;
}

function liveTotals(start, end) {
  const days = liveDates(start, end).map(liveDay);
  const result = {days: days.length, shop_days: 0, session_days: 0};
  for (const key of ['shop_gmv','gmv','hours','likes','buyers']) {
    const values = days.map(row => row[key]);
    result[key] = values.length && values.every(value => value != null) ? values.reduce((sum, value) => sum + value, 0) : null;
  }
  result.shop_days = days.filter(row => row.shop_gmv != null).length;
  result.session_days = days.filter(row => row.gmv != null).length;
  result.share = liveRatio(result.gmv, result.shop_gmv);
  return result;
}

function liveDelta(value, previous) {
  if (value == null || previous == null) return '<span class="live-neutral">暂无可比数据</span>';
  if (previous === 0) return `<span class="live-neutral">${value === 0 ? '→ 0.0%' : '上期为 0'}</span>`;
  const change = (value - previous) / Math.abs(previous);
  return `<span class="${change > 0 ? 'live-positive' : change < 0 ? 'live-negative' : 'live-neutral'}">${change > 0 ? '↑' : change < 0 ? '↓' : '→'} ${liveNumber(Math.abs(change * 100), 1)}%</span>`;
}

function liveChartOptions(dates, axis, title) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: {mode:'index', intersect:false},
    onClick(event, elements) {
      if (elements.length) {
        LIVE_STATE.date = dates[elements[0].index];
        renderLiveDay();
      }
    },
    plugins: {
      legend: {position:'bottom', labels:{usePointStyle:true, padding:18, color:'#52657c'}},
      tooltip: {callbacks:{label(context) {
        const value = context.raw;
        const formatted = context.dataset.yAxisID === 'share' ? liveRate(value) : context.dataset.yAxisID === 'hours' ? `${liveNumber(value,2)} 小时` : liveMoney(value);
        return `${context.dataset.label}：${formatted}`;
      }}}
    },
    scales: {
      x: {grid:{display:false}, ticks:{color:'#667c93',maxTicksLimit:9,maxRotation:45}},
      gmv: {type:'linear', position:'left', beginAtZero:true, title:{display:true,text:'GMV（人民币元）'}, ticks:{color:'#667c93',callback:value => liveNumber(value)}, grid:{color:'#eaf0f6'}},
      [axis]: {type:'linear',position:'right',beginAtZero:true,title:{display:true,text:title}, grid:{drawOnChartArea:false}, ticks:{color:'#667c93',callback:value => axis === 'share' ? `${liveNumber(value*100,0)}%` : liveNumber(value,1)}}
    }
  };
}

function renderLiveCharts() {
  const dates = liveDates(state.start, state.end), rows = dates.map(liveDay);
  const line = (label,key,color,axis='gmv') => ({label,data:rows.map(row => row[key]),borderColor:color,backgroundColor:color,yAxisID:axis,borderWidth:2.5,tension:.2,pointRadius:dates.length>60?0:2,pointHitRadius:14,pointHoverRadius:5,spanGaps:false});
  const labels = dates.map(date => date.slice(5));
  upsertChart('chart-live-gmv', {type:'line',data:{labels,datasets:[line('店铺 GMV','shop_gmv','#2787e7'),line('直播 GMV','gmv','#f09b3c'),line('直播 GMV 占比','share','#20a080','share')]},options:liveChartOptions(dates,'share','直播 GMV 占比（%）')});
  upsertChart('chart-live-hours', {type:'line',data:{labels,datasets:[line('店铺 GMV','shop_gmv','#2787e7'),line('直播时长','hours','#8565c4','hours')]},options:liveChartOptions(dates,'hours','直播时长（小时）')});
}

function renderLiveDay() {
  const input = document.getElementById('live-detail-date');
  input.min = LIVE_DETAIL_START; input.max = LIVE_DETAIL_END;
  if (!LIVE_STATE.date || LIVE_STATE.date < LIVE_DETAIL_START || LIVE_STATE.date > LIVE_DETAIL_END) {
    LIVE_STATE.date = LIVE_DATA.coverage.sessions_end;
  }
  input.value = LIVE_STATE.date;
  const day = liveDay(LIVE_STATE.date), sessions = LIVE_DAYS.get(LIVE_STATE.date) || [];
  const kpis = [['直播场次', `${sessions.length} 场`], ['直播时长', day.hours == null ? '—' : `${liveNumber(day.hours,2)} 小时`], ['当日直播 GMV',liveMoney(day.gmv)], ['当日店铺 GMV',liveMoney(day.shop_gmv)], ['当日直播占比',liveRate(day.share)]];
  document.getElementById('live-day-kpis').innerHTML = kpis.map(([label,value]) => `<div class="live-day-kpi"><span>${label}</span><strong>${value}</strong></div>`).join('');
  const empty = day.gmv == null ? '此日期超出直播明细数据范围，暂无场次数据。' : '此日期没有直播场次记录。';
  document.getElementById('live-timeline').innerHTML = sessions.length ? `<div class="live-axis"><span>开播时间 · 时长</span><div class="live-ticks"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div></div>` + sessions.map(session => {
    const startHours = Number(session.start.slice(11,13)) + Number(session.start.slice(14,16))/60 + Number(session.start.slice(17,19))/3600;
    const visibleHours = Math.min(session.hours,24-startHours);
    const title = `${session.start.replace('T',' ')} → ${session.end.replace('T',' ')} · ${liveNumber(session.hours,2)} 小时 · ${liveMoney(session.gmv)}`;
    return `<div class="live-timeline-row"><span>${session.start.slice(11,16)} · ${liveNumber(session.hours,2)} 小时</span><div class="live-track"><span class="live-bar" style="left:${startHours/24*100}%;width:${visibleHours/24*100}%" title="${liveEscape(title)}"></span></div></div>`;
  }).join('') : `<div class="live-empty">${empty}</div>`;
  document.getElementById('live-session-rows').innerHTML = sessions.length ? sessions.map(session => {
    const nextDay = session.end.slice(0,10) !== session.date;
    const end = `${session.end.slice(11)}${nextDay ? `（${session.end.slice(5,10)}）` : ''}`;
    return `<tr><td>${liveEscape(session.name)}<small>场次 ${liveEscape(session.id)}</small></td><td>${session.start.slice(11)}</td><td>${end}</td><td>${liveNumber(session.hours,2)}</td><td>${liveMoney(session.gmv)}</td><td>${liveMoney(day.shop_gmv)}</td><td>${liveRate(liveRatio(session.gmv,day.shop_gmv))}</td><td>${liveNumber(session.likes)}</td><td>${liveNumber(session.buyers)}</td></tr>`;
  }).join('') : `<tr><td colspan="9"><div class="live-empty">${empty}</div></td></tr>`;
}

function renderLivePage() {
  const sameMonth = LIVE_STATE.compareMode === 'month';
  const coverageStart = [LIVE_DATA.coverage.shop_start,LIVE_DATA.coverage.sessions_start].sort().at(-1);
  const coverageEnd = [LIVE_DATA.coverage.shop_end,LIVE_DATA.coverage.sessions_end].sort()[0];
  const effectiveStart = state.start < coverageStart ? coverageStart : state.start;
  const effectiveEnd = state.end > coverageEnd ? coverageEnd : state.end;
  const hasData = effectiveStart <= effectiveEnd;
  const previousStart = sameMonth ? shiftMonth(hasData ? effectiveStart : state.start,-1) : state.compareStart;
  const previousEnd = sameMonth ? shiftMonth(hasData ? effectiveEnd : state.end,-1) : state.compareEnd;
  const current = hasData ? liveTotals(effectiveStart,effectiveEnd) : {days:0,shop_days:0,session_days:0,shop_gmv:null,gmv:null,hours:null,likes:null,buyers:null,share:null};
  const previous = liveTotals(previousStart,previousEnd);
  const compareLabel = sameMonth ? '上月同期' : '对比期';
  document.getElementById('live-period').textContent = hasData ? `指标统计 ${effectiveStart} → ${effectiveEnd} · ${compareLabel} ${previousStart} → ${previousEnd}` : `查询 ${state.start} → ${state.end} · 暂无共同覆盖的直播与店铺数据`;
  const warnings = [];
  if (!hasData) warnings.push('查询范围内没有共同覆盖的直播与店铺数据。请调整顶部查询日期。');
  else if (effectiveStart !== state.start || effectiveEnd !== state.end) warnings.push(`查询 ${state.start} → ${state.end}；两表共同已到数据为 ${effectiveStart} → ${effectiveEnd}。六项指标按此区间计算${sameMonth ? '，上月同期同步对齐' : ''}；趋势保留完整查询范围，未到数据留空。`);
  if (current.shop_days !== current.days || current.session_days !== current.days) warnings.push(`查询期 ${current.days} 天，店铺数据覆盖 ${current.shop_days} 天，直播明细覆盖 ${current.session_days} 天。缺少数据的汇总指标显示“—”，曲线保留空缺。`);
  if (previous.shop_days !== previous.days || previous.session_days !== previous.days) warnings.push('对比期数据不完整，相关环比显示“暂无可比数据”。');
  document.getElementById('live-coverage').innerHTML = warnings.length ? `<div class="live-warning">${warnings.join(' ')}</div>` : '';
  const specs = [
    ['店铺 GMV','shop_gmv',liveMoney,''],['直播 GMV','gmv',liveMoney,''],['直播 GMV 占比','share',liveRate,''],
    ['直播时长','hours',value => liveNumber(value,2),'小时'],['Likes','likes',liveNumber,''],['买家数 Buyers','buyers',liveNumber,'']
  ];
  document.getElementById('live-kpis').innerHTML = specs.map(([label,key,format,unit]) => `<article class="live-card"><div class="live-label">${label}</div><div class="live-value">${format(current[key])}${unit?`<small>${unit}</small>`:''}</div><div class="live-comparison"><span>${compareLabel} ${format(previous[key])}</span>${liveDelta(current[key],previous[key])}</div></article>`).join('');
  document.getElementById('live-sources').innerHTML = `数据源：<a href="${liveEscape(LIVE_DATA.sources.daily)}" target="_blank" rel="noopener">SKT-SP-live · 店铺日数据</a> / <a href="${liveEscape(LIVE_DATA.sources.sessions)}" target="_blank" rel="noopener">Live-明细 · 直播场次</a>。店铺数据截至 ${LIVE_DATA.coverage.shop_end}，直播明细截至 ${LIVE_DATA.coverage.sessions_end}。日表直播销售为确认订单口径，本页统一使用明细表 Gross Sales，不混算；明细覆盖期内无场次记录的日期按 0 汇总。`;
  renderLiveCharts(); renderLiveDay();
}

document.getElementById('live-detail-date').addEventListener('change', event => {
  const selected = event.target.value;
  if (selected && selected >= LIVE_DETAIL_START && selected <= LIVE_DETAIL_END) { LIVE_STATE.date = selected; }
  renderLiveDay();
});
document.getElementById('live-compare-mode').addEventListener('change', event => {
  LIVE_STATE.compareMode = event.target.value;
  renderLivePage();
});
if (location.hash === '#live') state.activePage = 'live';
