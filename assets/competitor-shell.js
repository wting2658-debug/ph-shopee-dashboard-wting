const competitorFrame = document.getElementById('competitor-frame');
const competitorSubtitle = document.querySelector('.dashboard-subtitle');
const competitorOriginalSubtitle = competitorSubtitle.innerHTML;
let competitorStarted = false;
function syncCompetitorShell() {
  const active = state.activePage === 'competitor';
  document.querySelector('.dashboard-controls').hidden = active;
  document.querySelector('.hero-refresh').hidden = active;
  competitorSubtitle.innerHTML = active
    ? '查看菲律宾市场的店铺、商品月度排名及竞品机会；使用本模块独立的月份与类目筛选，区分自身表现和市场变化。'
    : competitorOriginalSubtitle;
}
function renderCompetitorPage() {
  if (competitorStarted) return;
  competitorStarted = true;
  competitorFrame.src = competitorFrame.dataset.src;
}
document.getElementById('competitor-reload').addEventListener('click', () => {
  document.getElementById('competitor-period').textContent = '正在重新加载月度排名数据…';
  const refreshed = new URL(competitorFrame.dataset.src, document.baseURI);
  refreshed.searchParams.set('reload', String(Date.now()));
  competitorFrame.src = refreshed.href;
});
window.addEventListener('message', event => {
  if (event.origin !== location.origin || event.source !== competitorFrame.contentWindow) return;
  const message = event.data;
  if (!message || message.type !== 'ph-competitor:status') return;
  if (Number.isFinite(message.height) && message.height >= 200 && message.height <= 100000) {
    competitorFrame.style.height = Math.ceil(message.height) + 'px';
  }
  const period = document.getElementById('competitor-period');
  if (message.error) period.textContent = '竞品数据暂时未能加载，请点击“重新加载”重试。';
  else if (typeof message.start === 'string' && typeof message.end === 'string') {
    period.textContent = `月度数据：${message.start} — ${message.end} · 更新于 ${String(message.updated || '').replace('T',' ').slice(0,19)}（北京时间） · 一级至四级类目独立筛选`;
  }
});
if (location.hash === '#competitor') state.activePage = 'competitor';
