// ===== Affiliate calculation helpers =====
const afRatio = (a, b) => a == null || b == null || !b ? null : a / b;
function afDates(start, end) {
  const result = [], cursor = new Date(`${start}T00:00:00Z`), last = new Date(`${end}T00:00:00Z`);
  while (Number.isFinite(+cursor) && cursor <= last) { result.push(cursor.toISOString().slice(0,10)); cursor.setUTCDate(cursor.getUTCDate()+1); }
  return result;
}
function afMatches(data, row, filters) {
  const product = data.products[row[1]];
  return (!filters.category || product[1] === filters.category) && (!filters.product || product[0] === filters.product) && (!filters.channel || data.channels[row[2]] === filters.channel);
}
function afAggregate(data, start, end, filters = {}) {
  const known = new Set(data.dates), requested = afDates(start,end), dates = requested.filter(d => known.has(d));
  const result = {gmv:0,cost:0,units:0,orders:0,days:dates.length,requested:requested.length,complete:requested.length>0 && dates.length===requested.length,rows:[]};
  for (const row of data.rows) {
    const d = data.dates[row[0]];
    if (d < start || d > end || !afMatches(data,row,filters)) continue;
    result.gmv += row[3]; result.cost += row[4]; result.units += row[5]; result.orders += row[6]; result.rows.push(row);
  }
  if (!dates.length) for (const key of ['gmv','cost','units','orders']) result[key]=null;
  result.roi = afRatio(result.gmv,result.cost); result.commissionRate = afRatio(result.cost,result.gmv);
  return result;
}
function afGroups(data, current, previous, dimension) {
  if (!current.days) return [];
  const groups = new Map();
  for (const [rows,isPrevious] of [[current.rows,false],[previous.rows,true]]) for (const row of rows) {
    const p = data.products[row[1]], key = dimension === 'product' ? p[0] : dimension === 'category' ? p[1] : data.channels[row[2]];
    if (!groups.has(key)) groups.set(key,{key,name:dimension==='product'?p[2]:key,category:p[1],gmv:0,cost:0,units:0,orders:0,previous:0});
    const group = groups.get(key);
    if (isPrevious) group.previous+=row[3];
    else { group.gmv+=row[3];group.cost+=row[4];group.units+=row[5];group.orders+=row[6]; }
  }
  return [...groups.values()].map(group=>({...group,roi:afRatio(group.gmv,group.cost),commissionRate:afRatio(group.cost,group.gmv),growth:group.gmv-group.previous})).sort((a,b)=>b.gmv-a.gmv);
}
function afStoreTotals(data, dates, storeMap) {
  const values = dates.map(d=>storeMap.has(d)?storeMap.get(d):data.shop_gmv[d]??null);
  return values.length && values.every(v=>v!=null)?values.reduce((a,b)=>a+b,0):null;
}
function afShopTotals(data, dates) {
  const rows = dates.map(d=>data.shop[d]), result={days:rows.filter(Boolean).length,total:dates.length};
  for (const [index,key] of ['gmv','cost','units','orders'].entries()) result[key]=dates.length && rows.every(Boolean)?rows.reduce((sum,row)=>sum+row[index],0):null;
  return result;
}
// ===== End Affiliate calculation helpers =====

let AFFILIATE_DATA = null, affiliateLoading = null;
const AF_STATE = {category:'',product:'',channel:'',day:'',compare:'month',sort:'gmv',minGmv:0};
const AF_STORE_GMV = new Map();
for (const row of PAYLOAD.facts) AF_STORE_GMV.set(row[FACT.date],(AF_STORE_GMV.get(row[FACT.date])||0)+row[FACT.gmv]);
const afEscape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const afNum = (n, digits=0) => n==null || !Number.isFinite(n)?'—':n.toLocaleString('zh-CN',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const afMoney = n => n==null?'—':`¥${afNum(n)}`;
const afPercent = n => n==null?'—':`${afNum(n*100,2)}%`;
function afDelta(current, previous, goodDirection=0) {
  if (current==null || previous==null) return '<span class="af-neutral">暂无可比数据</span>';
  if (!previous) return `<span class="af-neutral">${!current?'→ 0.0%':'上期为 0'}</span>`;
  const change = (current-previous)/Math.abs(previous), positive = goodDirection ? change*goodDirection>0 : null;
  return `<span class="${positive==null?'af-neutral':positive?'af-positive':'af-negative'}">${change>0?'↑':change<0?'↓':'→'} ${afNum(Math.abs(change)*100,1)}%</span>`;
}
function afSetOptions(id, values, all, selected) {
  const element=document.getElementById(id);
  element.innerHTML = `<option value="">${all}</option>`+values.map(([value,label])=>`<option value="${afEscape(value)}">${afEscape(label)}</option>`).join('');
  element.value=selected;
}
function afRenderFilters() {
  const data=AFFILIATE_DATA;
  afSetOptions('af-category',[...new Set(data.products.map(p=>p[1]))].sort().map(c=>[c,c]),'全部类目',AF_STATE.category);
  afSetOptions('af-product',data.products.filter(p=>!AF_STATE.category || p[1]===AF_STATE.category).map(p=>[p[0],`${p[2]} · ${p[0]}`]),'全部商品',AF_STATE.product);
  afSetOptions('af-channel',data.channels.map(c=>[c,c]),'全部渠道',AF_STATE.channel);
}
function afRanges() {
  if (AF_STATE.day && (AF_STATE.day<state.start || AF_STATE.day>state.end)) AF_STATE.day='';
  // Keep the shared query period even when affiliate data ends earlier.
  // Store GMV must use the same full period as Store Analysis.
  const start=AF_STATE.day || state.start;
  const end=AF_STATE.day || state.end;
  const previousStart=AF_STATE.compare==='month'?shiftMonth(start,-1):state.compareStart;
  const previousEnd=AF_STATE.compare==='month'?shiftMonth(end,-1):state.compareEnd;
  return {start,end,previousStart,previousEnd};
}
function afCoveredRanges(data, range, mode) {
  const covered=data.dates.filter(d=>d>=range.start && d<=range.end);
  const start=covered[0] || range.start, end=covered.at(-1) || range.end;
  return {start,end,
    previousStart:mode==='month'?shiftMonth(start,-1):range.previousStart,
    previousEnd:mode==='month'?shiftMonth(end,-1):range.previousEnd};
}
function afChartOptions() {
  return {responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{usePointStyle:true,padding:16,color:'#52657c'}}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:9,maxRotation:45,color:'#667c93'}},y:{beginAtZero:true,grid:{color:'#eaf0f6'},ticks:{color:'#667c93'}}}};
}
function afToggle(dimension,value) {
  AF_STATE[dimension]=AF_STATE[dimension]===value?'':value;
  if (dimension==='category') AF_STATE.product='';
  if (dimension==='product' && AF_STATE.product) AF_STATE.category=AFFILIATE_DATA.products.find(p=>p[0]===value)[1];
  afRenderFilters(); renderAffiliatePage();
}
// Finish Chart.js event dispatch before destroying/rebuilding the active chart.
function afChartDrill(dimension,value) {
  requestAnimationFrame(()=>{if(state.activePage==='affiliate')afToggle(dimension,value);});
}
function afRenderCharts(current, previous, products) {
  const data=AFFILIATE_DATA, dates=afDates(state.start,state.end), known=new Set(data.dates), dayRows=new Map();
  const previousStart=AF_STATE.compare==='month'?shiftMonth(state.start,-1):state.compareStart;
  const previousEnd=AF_STATE.compare==='month'?shiftMonth(state.end,-1):state.compareEnd;
  const previousDates=afDates(previousStart,previousEnd),length=Math.max(dates.length,previousDates.length);
  for (const row of data.rows) {
    const d=data.dates[row[0]];
    if(!((d>=state.start && d<=state.end)||(d>=previousStart && d<=previousEnd)) || !afMatches(data,row,AF_STATE)) continue;
    if(!dayRows.has(d)) dayRows.set(d,{gmv:0,cost:0});
    dayRows.get(d).gmv+=row[3];dayRows.get(d).cost+=row[4];
  }
  const daily=periodDates=>Array.from({length},(_,i)=>{
    const d=periodDates[i],row=d && known.has(d)?dayRows.get(d)||{gmv:0,cost:0}:{gmv:null,cost:null};
    const shop=d?(AF_STORE_GMV.has(d)?AF_STORE_GMV.get(d):data.shop_gmv[d]??null):null;
    return {...row,shop,share:afRatio(row.gmv,shop),roi:afRatio(row.gmv,row.cost)};
  });
  const rows=daily(dates),previousRows=daily(previousDates);
  const line=(label,key,color,axis='y',isPrevious=false)=>({label:`${label} · ${isPrevious?'上期':'本期'}`,data:(isPrevious?previousRows:rows).map(row=>row[key]),afDates:isPrevious?previousDates:dates,borderColor:isPrevious?`${color}66`:color,backgroundColor:isPrevious?`${color}66`:color,yAxisID:axis,borderWidth:isPrevious?1.5:2.5,borderDash:isPrevious?[6,4]:[],order:isPrevious?1:0,tension:.2,pointRadius:length>90||isPrevious?0:2,pointHitRadius:15,spanGaps:false});
  const trendPeriod=`本期 ${state.start} → ${state.end} · 上期 ${previousStart} → ${previousEnd}；实线为本期，同色虚线为上期，按区间第 N 天对齐，缺失日期留空。`;
  document.getElementById('af-gmv-trend-period').textContent=`左轴：人民币元 · 右轴：占全店 GMV。${trendPeriod}`;
  document.getElementById('af-cost-trend-period').textContent=`左轴：预估佣金 · 右轴：投入产出比。${trendPeriod}`;
  for(const [id,axis,title,datasets] of [
    ['chart-af-gmv','share','联盟占比',[line('店铺 GMV','shop','#2787e7'),line('联盟 GMV','gmv','#f09b3c'),line('联盟占比','share','#20a080','share'),line('店铺 GMV','shop','#2787e7','y',true),line('联盟 GMV','gmv','#f09b3c','y',true),line('联盟占比','share','#20a080','share',true)]],
    ['chart-af-cost','roi','投入产出比',[line('预估佣金','cost','#8565c4'),line('投入产出比','roi','#20a080','roi'),line('预估佣金','cost','#8565c4','y',true),line('投入产出比','roi','#20a080','roi',true)]]
  ]) {
    const options=afChartOptions(); options.onClick=(event,elements)=>{if(elements.length && known.has(dates[elements[0].index])) afChartDrill('day',dates[elements[0].index]);};
    options.scales.y.title={display:true,text:'人民币元'};
    options.scales[axis]={type:'linear',position:'right',beginAtZero:true,title:{display:true,text:title},grid:{drawOnChartArea:false},ticks:{callback:v=>axis==='share'?afPercent(v):`${afNum(v,1)}×`}};
    options.plugins.tooltip={callbacks:{title:items=>{const i=items[0].dataIndex;return `本期 ${dates[i]||'无对应日期'} / 上期 ${previousDates[i]||'无对应日期'}`;},label:ctx=>`${ctx.dataset.label}（${ctx.dataset.afDates[ctx.dataIndex]||'无对应日期'}）：${ctx.dataset.yAxisID==='share'?afPercent(ctx.raw):ctx.dataset.yAxisID==='roi'?`${afNum(ctx.raw,2)}×`:afMoney(ctx.raw)}`}};
    upsertChart(id,{type:'line',data:{labels:Array.from({length},(_,i)=>dates[i]?.slice(5)||`上期 ${previousDates[i].slice(5)}`),datasets},options});
  }
  const categories=afGroups(data,current,previous,'category');
  const catOptions=afChartOptions();catOptions.indexAxis='y';catOptions.plugins.legend.display=false;catOptions.onClick=(event,elements)=>{if(elements.length)afChartDrill('category',categories[elements[0].index].key);};
  upsertChart('chart-af-category',{type:'bar',data:{labels:categories.map(c=>c.key),datasets:[{label:'联盟 GMV（¥）',data:categories.map(c=>c.gmv),backgroundColor:'#62a6d9',borderRadius:5}]},options:catOptions});
  const eligible=products.filter(p=>p.gmv>0 && p.gmv>=AF_STATE.minGmv);
  const bubbleOptions=afChartOptions();bubbleOptions.interaction={mode:'nearest',intersect:true};bubbleOptions.plugins.legend.display=false;bubbleOptions.scales.x={type:'linear',beginAtZero:true,title:{display:true,text:'联盟 GMV（¥）'},grid:{color:'#eaf0f6'}};bubbleOptions.scales.y.title={display:true,text:'佣金率'};bubbleOptions.scales.y.ticks={callback:afPercent};
  bubbleOptions.plugins.tooltip={callbacks:{label:ctx=>{const p=eligible[ctx.dataIndex];return `${p.name} · GMV ${afMoney(p.gmv)} · 佣金率 ${afPercent(p.commissionRate)} · ${afNum(p.units)} 件`;}}};
  bubbleOptions.onClick=(event,elements)=>{if(elements.length)afChartDrill('product',eligible[elements[0].index].key);};
  upsertChart('chart-af-efficiency',{type:'bubble',data:{datasets:[{label:'联盟商品',data:eligible.map(p=>({x:p.gmv,y:p.commissionRate,r:Math.max(4,Math.min(20,Math.sqrt(p.units)/3))})),backgroundColor:'rgba(39,135,160,.5)',borderColor:'#2787a0'}]},options:bubbleOptions});
}
function afRenderTables(current, previous, products) {
  const complete=current.complete && previous.complete, data=AFFILIATE_DATA;
  const cell=(value,formatter=afNum)=>`<td>${formatter(value)}</td>`;
  const link=(dimension,key,name)=>`<button type="button" class="af-link" data-af-dimension="${dimension}" data-af-key="${afEscape(key)}">${afEscape(name)}</button>`;
  document.getElementById('af-category-rows').innerHTML=afGroups(data,current,previous,'category').map(g=>`<tr${AF_STATE.category===g.key?' class="af-selected"':''}><td>${link('category',g.key,g.name)}</td>${cell(g.gmv,afMoney)}<td>${afDelta(g.gmv,complete?g.previous:null,1)}</td>${cell(g.cost,afMoney)}${cell(g.commissionRate,afPercent)}${cell(g.units)}</tr>`).join('') || '<tr><td colspan="6" class="af-empty">当前条件下暂无类目数据</td></tr>';
  document.getElementById('af-channel-rows').innerHTML=afGroups(data,current,previous,'channel').map(g=>`<tr${AF_STATE.channel===g.key?' class="af-selected"':''}><td>${link('channel',g.key,g.name)}</td>${cell(g.gmv,afMoney)}${cell(afRatio(g.gmv,current.gmv),afPercent)}${cell(g.cost,afMoney)}${cell(g.roi,n=>n==null?'—':`${afNum(n,2)}×`)}${cell(g.units)}</tr>`).join('') || '<tr><td colspan="6" class="af-empty">当前条件下暂无渠道数据</td></tr>';
  let ranked=products.filter(p=>p.gmv>=AF_STATE.minGmv);
  if(AF_STATE.sort==='roi')ranked=ranked.filter(p=>p.roi!=null);
  ranked.sort((a,b)=>{const av=a[AF_STATE.sort],bv=b[AF_STATE.sort];if(av==null)return bv==null?b.gmv-a.gmv:1;if(bv==null)return -1;return (AF_STATE.sort==='commissionRate'?av-bv:bv-av)||b.gmv-a.gmv;});
  document.getElementById('af-product-summary').textContent=`${ranked.length} 个商品 · GMV 环比按上方标注的联盟统计期及对比期计算；点击商品联动趋势、渠道与指标。`;
  document.getElementById('af-product-rows').innerHTML=ranked.map(p=>`<tr${AF_STATE.product===p.key?' class="af-selected"':''}><td>${link('product',p.key,p.name)}<small>${afEscape(p.key)}</small></td><td>${afEscape(p.category)}</td>${cell(p.gmv,afMoney)}<td>${afDelta(p.gmv,complete?p.previous:null,1)}</td>${cell(afRatio(p.gmv,current.gmv),afPercent)}${cell(p.cost,afMoney)}${cell(p.commissionRate,afPercent)}${cell(p.roi,n=>n==null?'—':`${afNum(n,2)}×`)}${cell(p.units)}${cell(p.orders)}</tr>`).join('') || '<tr><td colspan="10" class="af-empty">没有符合条件的商品，请调整筛选或最低 GMV。</td></tr>';
}
async function renderAffiliatePage() {
  if (!AFFILIATE_DATA) {
    document.getElementById('af-status').innerHTML='<div class="af-empty">正在加载联盟数据…</div>';
    if (!affiliateLoading) affiliateLoading=fetch('assets/affiliate-data.json').then(response=>{if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json();}).then(data=>{if(data.schema!==1 || !data.rows?.length)throw Error('数据格式不符');AFFILIATE_DATA=data;afRenderFilters();}).catch(error=>{affiliateLoading=null;document.getElementById('af-status').innerHTML='<div class="af-warning">联盟数据加载失败，请检查网络并<button type="button" class="af-link" id="af-retry">重试</button>。</div>';document.getElementById('af-retry').onclick=()=>renderAffiliatePage();throw error;});
    try {await affiliateLoading;} catch {return;}
    if(state.activePage==='affiliate') renderAffiliatePage();
    return;
  }
  const data=AFFILIATE_DATA, query=afRanges();
  const {start,end,previousStart,previousEnd}=afCoveredRanges(data,query,AF_STATE.compare);
  document.getElementById('last-updated').textContent=`最新更新：${PAYLOAD.generated_at}`;
  const current=afAggregate(data,start,end,AF_STATE),previous=afAggregate(data,previousStart,previousEnd,AF_STATE);
  const comparable=current.complete && previous.complete;
  document.querySelector('#af-sort option[value="growth"]').disabled=!comparable;
  if(!comparable && AF_STATE.sort==='growth'){AF_STATE.sort='gmv';document.getElementById('af-sort').value='gmv';}
  const dates=afDates(start,end),previousDates=afDates(previousStart,previousEnd);
  current.store=afStoreTotals(data,afDates(query.start,query.end),AF_STORE_GMV);
  previous.store=afStoreTotals(data,afDates(query.previousStart,query.previousEnd),AF_STORE_GMV);
  // Affiliate share and comparisons use the affiliate period, while the store
  // card retains the complete shared query period used by Store Analysis.
  const coveredStore=afStoreTotals(data,dates,AF_STORE_GMV),previousCoveredStore=afStoreTotals(data,previousDates,AF_STORE_GMV);
  current.share=current.complete?afRatio(current.gmv,coveredStore):null;
  previous.share=previous.complete?afRatio(previous.gmv,previousCoveredStore):null;
  const compareLabel=AF_STATE.compare==='month'?'上月同期':'对比期';
  const periodNote=`联盟统计 ${start} → ${end}（${current.days} 天） · ${compareLabel} ${previousStart} → ${previousEnd}（${previous.days} 天）`;
  document.getElementById('af-period').textContent=`查询 ${query.start} → ${query.end} · ${periodNote}`;
  document.getElementById('af-table-period').textContent=`${periodNote}；GMV 环比 =（本期 GMV − 上期 GMV）÷ 上期 GMV。`;
  const selectedProduct=data.products.find(p=>p[0]===AF_STATE.product);
  document.getElementById('af-selection').textContent=`当前筛选：${AF_STATE.category||'全部类目'} / ${selectedProduct?.[2]||'全部商品'} / ${AF_STATE.channel||'全部渠道'}${AF_STATE.day?` / ${AF_STATE.day}（趋势下钻）`:''}`;
  const warnings=[];
  if(!current.days)warnings.push('查询期没有联盟数据，相关指标显示“—”，请调整顶部日期或点击“最新有数月份”。');
  else if(start!==query.start || end!==query.end)warnings.push(`店铺 GMV 按完整查询期 ${query.start} → ${query.end} 统计，与“店铺分析”一致。${periodNote}；全部联盟指标、类目及商品环比使用这两个明确区间。联盟占比的分母为联盟统计期同日全店 GMV ${afMoney(coveredStore)}，不包含缺少联盟数据的日期。`);
  if(current.days && !current.complete)warnings.push('联盟统计期内存在缺日，金额为已覆盖日合计，占比及环比暂不计算；未覆盖日期不计为零。');
  if(!previous.complete)warnings.push('对比期商品数据不完整，相关环比显示“暂无可比数据”。');
  if(current.store==null)warnings.push('部分查询日缺少全店 GMV，店铺 GMV 及占全店比例显示“—”。');
  document.getElementById('af-status').innerHTML=warnings.length?`<div class="af-warning">${warnings.map(afEscape).join(' ')}</div>`:'';
  const specs=[['店铺 GMV · 全店基准','store',afMoney,1],['联盟 GMV','gmv',afMoney,1],['联盟花费 · 预估佣金','cost',afMoney,0],['联盟占全店 GMV','share',afPercent,1],['联盟卖出数量 · 件','units',afNum,1],['联盟商品订单 · 未跨品去重','orders',afNum,1],['联盟投入产出比','roi',n=>n==null?'—':`${afNum(n,2)}×`,1],['联盟佣金率','commissionRate',afPercent,-1]];
  document.getElementById('af-kpis').innerHTML=specs.map(([label,key,format,direction])=>{
    const canCompare=key==='store'?current.store!=null&&previous.store!=null:comparable;
    const period=key==='store'?`${query.start} → ${query.end}`:`${start} → ${end}${!current.complete?` · 已覆盖 ${current.days}/${current.requested} 天`:''}${key==='share'?` · 同期全店 ${afMoney(coveredStore)}`:''}`;
    const comparisonPeriod=key==='store'?`${query.previousStart} → ${query.previousEnd}`:`${previousStart} → ${previousEnd}`;
    return `<article class="af-card" data-af-metric="${key}"><div class="af-label">${label}</div><div class="af-value">${format(current[key])}</div><div class="af-card-period">${period}</div><div class="af-comparison"><span>${compareLabel} ${canCompare?format(previous[key]):'—'}</span>${afDelta(current[key],canCompare?previous[key]:null,direction)}</div><div class="af-card-period">对比 ${comparisonPeriod}</div></article>`;
  }).join('');
  const products=afGroups(data,current,previous,'product');
  afRenderCharts(current,previous,products);afRenderTables(current,previous,products);
  const shop=afShopTotals(data,afDates(query.start,query.end)),unfiltered=afAggregate(data,start,end,{}),differences=data.audit.shop_reconciliation_differences.filter(d=>d.date>=query.start&&d.date<=query.end);
  document.getElementById('af-shop-summary').innerHTML=`<div>店铺日表覆盖<strong>${shop.days} / ${shop.total} 天</strong></div><div>店铺报表联盟 GMV<strong>${afMoney(shop.gmv)}</strong></div><div>店铺报表联盟佣金<strong>${afMoney(shop.cost)}</strong></div><div>店铺报表售出数量<strong>${afNum(shop.units)}</strong></div><div>平台店铺订单<strong>${afNum(shop.orders)}</strong></div>`;
  document.getElementById('af-sources').innerHTML=`<a href="${afEscape(data.source)}" target="_blank" rel="noopener">联盟商品明细</a>覆盖 ${data.coverage.start} → ${data.coverage.end}（${data.coverage.days} 天 / ${afNum(data.rows.length)} 行）。本模块指标、类目和排行统一使用商品明细；全店 GMV 优先使用“店铺分析”的全产品人民币数据，历史缺口使用源表每日店铺 GMV，按日取一次。<a href="${afEscape(data.shop_source)}" target="_blank" rel="noopener">平台店铺日表</a>为独立核对基准，保留全店口径，不受商品及渠道筛选影响；覆盖不全时汇总留空。${differences.length?`当前区间有 ${differences.length} 天店铺日表与商品明细的 GMV / 佣金 / 件数存在差异，保留两个来源的原值，不强行调平。全商品明细 GMV 为 ${afMoney(unfiltered.gmv)}。`:''} 店铺订单为平台每日订单之和，商品订单为商品渠道记录之和，均不代表跨日去重买家数。`;
}
for(const key of ['category','product','channel','compare','sort'])document.getElementById(`af-${key}`).addEventListener('change',event=>{
  AF_STATE[key]=event.target.value;
  if(key==='category')AF_STATE.product='';
  if(key==='product' && AF_STATE.product)AF_STATE.category=AFFILIATE_DATA.products.find(p=>p[0]===AF_STATE.product)[1];
  afRenderFilters();renderAffiliatePage();
});
document.getElementById('af-min-gmv').addEventListener('input',event=>{AF_STATE.minGmv=Math.max(0,Number(event.target.value)||0);renderAffiliatePage();});
document.getElementById('af-reset').addEventListener('click',()=>{Object.assign(AF_STATE,{category:'',product:'',channel:'',day:'',sort:'gmv',minGmv:0});document.getElementById('af-sort').value='gmv';document.getElementById('af-min-gmv').value='0';if(AFFILIATE_DATA)afRenderFilters();renderAffiliatePage();});
document.getElementById('af-latest').addEventListener('click',()=>{if(!AFFILIATE_DATA)return;state.end=AFFILIATE_DATA.coverage.end;state.start=state.end.slice(0,7)+'-01';AF_STATE.day='';state.compareStart=shiftMonth(state.start,-1);state.compareEnd=shiftMonth(state.end,-1);syncDateInputs();renderAll();});
document.getElementById('affiliate-page').addEventListener('click',event=>{const button=event.target.closest('[data-af-dimension]');if(button)afToggle(button.dataset.afDimension,button.dataset.afKey);});
if(location.hash==='#affiliate')state.activePage='affiliate';
