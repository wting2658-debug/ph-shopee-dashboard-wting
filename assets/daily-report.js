// ===== Daily report calculation helpers =====
const dpValid = value => typeof value === 'number' && Number.isFinite(value);
const dpRatio = (a,b) => dpValid(a) && dpValid(b) && b !== 0 ? a/b : null;
const dpSum = values => values.length && values.every(dpValid) ? values.reduce((a,b)=>a+b,0) : null;
const dpChange = (a,b) => dpValid(a) && dpValid(b) && b !== 0 ? a/b-1 : null;
function dpDates(start,end) {
  const dates=[],day=new Date(start+'T00:00:00Z'),last=new Date(end+'T00:00:00Z');
  while (Number.isFinite(+day) && day<=last && dates.length<3660) {
    dates.push(day.toISOString().slice(0,10));day.setUTCDate(day.getUTCDate()+1);
  }
  return dates;
}
function dpPreviousDay(day) {
  const d=new Date(day+'T00:00:00Z'),n=d.getUTCDate();
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-1);
  const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();
  // A day without a matching date in the previous month has no daily comparison.
  return n>last?null:new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),n)).toISOString().slice(0,10);
}
function dpStoreDays(rows) {
  const byDay=new Map();
  for (const row of rows) {
    const day=row[FACT.date];
    if(!byDay.has(day))byDay.set(day,createAgg());
    addFact(byDay.get(day),row);
  }
  return new Map([...byDay].map(([day,agg])=>[day,dpFinalize(agg)]));
}
function dpFinalize(agg) {
  return {...agg,totalSpend:agg.adSpend+agg.metaSpend,
    averageOrderValue:dpRatio(agg.gmv,agg.orders),conversion:dpRatio(agg.orders,agg.clicks),clickRate:dpRatio(agg.clicks,agg.visitors),
    cpc:dpRatio(agg.adSpend,agg.adClicks),adCTR:dpRatio(agg.adClicks,agg.impressions),adCVR:dpRatio(agg.adOrders,agg.adClicks),
    adROI:dpRatio(agg.adGMV,agg.adSpend),metaCTR:dpRatio(agg.metaClicks,agg.metaImpressions),
    metaCVR:dpRatio(agg.metaPurchases,agg.metaClicks),metaROAS:dpRatio(agg.metaGMV,agg.metaSpend),metaCPM:dpRatio(agg.metaSpend*1000,agg.metaImpressions),
    onsiteFee:dpRatio(agg.adSpend,agg.gmv),offsiteFee:dpRatio(agg.metaSpend,agg.gmv),totalFee:dpRatio(agg.adSpend+agg.metaSpend,agg.gmv)};
}
function dpPeriod(dates,byDay) {
  if(!dates.length || dates.some(d=>!byDay.has(d)))return null;
  const agg=createAgg();
  for(const day of dates)for(const key of Object.keys(agg))agg[key]+=byDay.get(day)[key];
  return dpFinalize(agg);
}
function dpBuyerPeriod(dates,shop) {
  return {newBuyers:dpSum(dates.map(d=>shop[d]?.newBuyers)),buyers:dpSum(dates.map(d=>shop[d]?.buyers))};
}
function dpAffiliatePeriod(current,previous,costs,byDay) {
  const indexes=current.map((day,i)=>dpValid(costs[day]) && byDay.has(day)?i:-1).filter(i=>i>=0);
  const dates=indexes.map(i=>current[i]),compareDates=indexes.map(i=>previous[i]);
  const rate=days=>dpRatio(dpSum(days.map(d=>costs[d])),dpSum(days.map(d=>byDay.get(d)?.gmv)));
  return {current:rate(dates),previous:rate(compareDates),dates,compareDates};
}
function dpTopTen(rows,currentDates,compareDates,dimension) {
  const cur=new Set(currentDates),prev=new Set(compareDates),map=new Map();
  for(const row of rows) {
    const day=row[FACT.date],id=row[FACT.id];
    if(!cur.has(day) && !prev.has(day))continue;
    if(!map.has(id))map.set(id,{id,current:createAgg(),previous:createAgg()});
    if(cur.has(day))addFact(map.get(id).current,row);
    if(prev.has(day))addFact(map.get(id).previous,row);
  }
  return [...map.values()].filter(r=>dimension.get(r.id)?.has_store && r.current.gmv>0)
    .sort((a,b)=>b.current.gmv-a.current.gmv || a.id.localeCompare(b.id)).slice(0,10)
    .map((r,i)=>({...r,rank:i+1,current:dpFinalize(r.current),previous:dpFinalize(r.previous)}));
}

// ===== Daily report rendering =====
let DAILY_REPORT_DATA=null,dpLoading=null,dpDayCache=null;
let dpCaptureLibrary=null,dpExportBusy=false;
const DP_STATE={salesMonth:null,sortKey:'gmv',sortDirection:'desc'};
const dpEl=id=>document.getElementById(id);
const dpEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dpFormat(value,kind='number') {
  if(!dpValid(value))return '—';
  if(kind==='percent')return (value*100).toFixed(2)+'%';
  if(kind==='wan')return (value/10000).toFixed(1)+'万';
  if(kind==='ratio')return value.toFixed(2);
  if(kind==='decimal')return value.toFixed(2);
  return (kind==='money'?'¥':'')+value.toLocaleString('en-US',{maximumFractionDigits:0});
}
function dpDelta(current,previous,points=false) {
  const value=points?(dpValid(current)&&dpValid(previous)?(current-previous)*100:null):dpChange(current,previous);
  if(!dpValid(value))return '<span class="dp-delta dp-neutral">—</span>';
  const rounded=Number((points?value:value*100).toFixed(points?2:1)),sign=rounded>0?'+':'';
  return `<span class="dp-delta ${rounded>0?'dp-up':rounded<0?'dp-down':'dp-neutral'}">${rounded>0?'↗ ':rounded<0?'↘ ':''}${sign}${rounded.toFixed(points?2:1)}${points?'PT':'%'}</span>`;
}
function dpMetricCard(label,current,previous,kind='number',note='') {
  return `<article class="dp-card"><div class="dp-card-label">${label}</div><div class="dp-card-main"><strong class="dp-value">${dpFormat(current,kind)}</strong>${dpDelta(current,previous)}</div><div class="dp-card-foot">对比期 ${dpFormat(previous,kind)}${note?'<br>'+dpEscape(note):''}</div></article>`;
}
function dpRenderOverview() {
  const rows=SUBSIDY_DATA.sales,months=[...new Set(rows.map(r=>r.month))].sort().reverse();
  if(!months.includes(DP_STATE.salesMonth))DP_STATE.salesMonth=months[0];
  dpEl('dp-sales-month').innerHTML=months.map(m=>`<option ${m===DP_STATE.salesMonth?'selected':''}>${m}</option>`).join('');
  const selected=rows.filter(r=>r.month===DP_STATE.salesMonth),tt=selected.find(r=>r.platform==='TT'),shelf=selected.find(r=>r.platform==='货架');
  const total=dpSum([tt?.actual,shelf?.actual]),target=dpSum([tt?.target,shelf?.target]);
  const kpi=(label,value,goal,rate)=>`<div><div class="dp-card-label">${label}</div><strong class="dp-value" title="${dpFormat(value,'money')}">${dpFormat(value,'wan')}</strong><div class="dp-attainment">${dpFormat(rate,'percent')}</div><div class="dp-progress"><span style="width:${dpValid(rate)?Math.max(0,Math.min(100,rate*100)):0}%"></span></div><div class="dp-target">目标 ${dpFormat(goal,'wan')}</div></div>`;
  dpEl('dp-sales-overview').innerHTML=kpi('全渠道累计达成',total,target,dpRatio(total,target))+kpi('TT 累计达成',tt?.actual,tt?.target,tt?.achievement)+kpi('货架累计达成',shelf?.actual,shelf?.target,shelf?.achievement)+`<div class="dp-side-kpis"><div><span>货架环比</span>${dpDelta(shelf?.actual,shelf?.previous)}</div><div><span>货架 SOB</span><strong>${dpFormat(shelf?.share,'percent')}</strong></div><div><span>TT 环比</span>${dpDelta(tt?.actual,tt?.previous)}</div><div><span>TT SOB</span><strong>${dpFormat(tt?.share,'percent')}</strong></div></div>`;
}
function dpChart(id,currentDates,previousDates,valueOf,kind='number') {
  const length=Math.max(currentDates.length,previousDates.length),indexes=Array.from({length},(_,i)=>i),sets=[currentDates,previousDates];
  const currentChartColor='#2787e7',compareChartColor='#9bbde6';
  const compact=value=>kind==='percent'?(Number(value)*100).toFixed(1)+'%':Math.abs(value)>=10000?(value/10000).toFixed(1)+'万':dpFormat(value);
  upsertChart(id,{type:'line',data:{labels:indexes.map(i=>(currentDates[i]||previousDates[i]||'').slice(5)),datasets:sets.map((dates,i)=>({label:i?'对比期':'本期',data:indexes.map(n=>dates[n]?valueOf(dates[n]):null),borderColor:i?compareChartColor:currentChartColor,backgroundColor:i?compareChartColor:currentChartColor,borderDash:i?[5,5]:[],borderWidth:i?2:2.8,pointRadius:0,pointHitRadius:10,tension:.22,spanGaps:false}))},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{title:items=>items.length?'区间第 '+(items[0].dataIndex+1)+' 天':'',label:ctx=>`${ctx.dataset.label} · ${sets[ctx.datasetIndex][ctx.dataIndex]??'—'}：${dpFormat(ctx.parsed.y,kind)}`}}},scales:{x:{grid:{display:false},ticks:{color:'#7c8fa3',maxTicksLimit:5,maxRotation:0,font:{size:11}}},y:{beginAtZero:true,grid:{color:'#edf2f6'},ticks:{color:'#7c8fa3',maxTicksLimit:4,font:{size:11},callback:compact}}}}});
}
const DP_EXPENSE_METRICS=[
  ['onsite-spend','站内花费','adSpend','money'],
  ['onsite-fee','站内费比','onsiteFee','percent'],
  ['offsite-spend','站外花费','metaSpend','money'],
  ['offsite-fee','站外费比','offsiteFee','percent']
];
function dpRenderCharts(current,previous,byDay,channelByDay) {
  for(const [id,key,kind] of [['sp-sales','sp_gmv','money'],['sp-subsidy','sp_rate','percent'],['tt-sales','tt_gmv','money'],['tt-subsidy','tt_rate','percent']])
    dpChart('dp-chart-'+id,current,previous,day=>channelByDay.get(day)?.[key]??null,kind);
  for(const [id,,key,kind] of DP_EXPENSE_METRICS)
    dpChart('dp-chart-'+id,current,previous,day=>byDay.get(day)?.[key]??null,kind);
  for(const [id,key,kind] of [['sales','gmv','money'],['clicks','clicks','number'],['cvr','conversion','percent']])
    dpChart('dp-chart-store-'+id,current,previous,day=>byDay.get(day)?.[key]??null,kind);
}
function dpRenderRecent(current,byDay,channelByDay,shop) {
  const recent=current.slice(-7).reverse();
  const cell=(a,b,kind='number',points=false)=>`<td>${dpFormat(a,kind)} ${dpDelta(a,b,points)}</td>`;
  dpEl('dp-recent-channels').innerHTML='<thead><tr>'+['日期','全渠道 GMV','货架 GMV','货架 SOB / 环比','TikTok GMV'].map(s=>`<th>${s}</th>`).join('')+'</tr></thead><tbody>'+recent.map(day=>{
    const r=channelByDay.get(day),p=channelByDay.get(dpPreviousDay(day));
    return `<tr><td>${day.slice(5)}</td><td>${dpFormat(r?.total,'wan')}</td><td>${dpFormat(r?.shelf,'wan')}</td>${cell(dpRatio(r?.shelf,r?.total),dpRatio(p?.shelf,p?.total),'percent',true)}<td>${dpFormat(r?.tt_gmv,'wan')}</td></tr>`;
  }).join('')+'</tbody>';
  dpEl('dp-recent-store').innerHTML='<thead><tr>'+['日期','Sales / 环比','访客 / 环比','点击 / 环比','AOV / 环比','订单 / 环比','CVR / 环比','新买家占比 / 环比'].map(s=>`<th>${s}</th>`).join('')+'</tr></thead><tbody>'+recent.map(day=>{
    const prev=dpPreviousDay(day),r=byDay.get(day),p=byDay.get(prev),buyer=shop[day],pb=shop[prev];
    return `<tr><td>${day.slice(5)}</td>${cell(r?.gmv,p?.gmv,'wan')}${cell(r?.visitors,p?.visitors)}${cell(r?.clicks,p?.clicks)}${cell(r?.averageOrderValue,p?.averageOrderValue)}${cell(r?.orders,p?.orders)}${cell(r?.conversion,p?.conversion,'percent')}${cell(dpRatio(buyer?.newBuyers,buyer?.buyers),dpRatio(pb?.newBuyers,pb?.buyers),'percent')}</tr>`;
  }).join('')+'</tbody>';
}
const DP_PRODUCT_COLUMNS=[
  ['gmv','Sales￥','money'],['share','GMV 占比','percent'],['clicks','点击','number'],['conversion','CVR','percent'],['clickRate','CTR','percent'],['averageOrderValue','AOV￥','money'],['orders','订单量','number'],['totalSpend','总花费￥','money'],['visitors','访客','number'],
  ['adSpend','站内花费￥','money'],['impressions','站内曝光','number'],['adClicks','站内点击','number'],['cpc','站内 CPC','decimal'],['adCVR','站内 CVR','percent'],['adGMV','站内 Sales￥','money'],['adROI','站内 ROI','ratio'],
  ['metaSpend','站外花费￥','money'],['metaImpressions','站外曝光','number'],['metaClicks','站外点击','number'],['metaCTR','站外 CTR','percent'],['metaCPM','站外 CPM','decimal'],['metaGMV','站外 Sales￥','money'],['metaROAS','站外 ROI','ratio']
];
function dpRenderTop(current,previous,total,compareTotal) {
  const comparisonAvailable=Boolean(compareTotal),rows=dpTopTen(facts,current,previous,productMap).map(r=>({...r,current:{...r.current,share:dpRatio(r.current.gmv,total?.gmv)},previous:{...r.previous,share:dpRatio(r.previous.gmv,compareTotal?.gmv)}}));
  const key=DP_STATE.sortKey,sign=DP_STATE.sortDirection==='asc'?1:-1;
  rows.sort((a,b)=>((a.current[key]??-Infinity)-(b.current[key]??-Infinity))*sign || a.rank-b.rank);
  dpEl('dp-top-products').innerHTML='<thead><tr><th>#</th><th>产品链接</th>'+DP_PRODUCT_COLUMNS.map(([key,label])=>`<th><button class="dp-sort" type="button" data-dp-sort="${key}">${label} ${DP_STATE.sortKey===key?(DP_STATE.sortDirection==='asc'?'↑':'↓'):'↕'}</button></th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>{
    const p=productMap.get(r.id),ids=String(p.product_ids??'').match(/\d+/g)||[],url=ids.length===1?'https://shopee.ph/product/612831390/'+ids[0]:'';
    const name=dpEscape(p.product_name||p.id);
    return `<tr><td>${r.rank}</td><td>${url?`<a class="dp-product-link" href="${url}" target="_blank" rel="noopener">${name}</a>`:`<span class="dp-product-link" title="${dpEscape(p.product_ids)}">${name}</span>`}</td>`+DP_PRODUCT_COLUMNS.map(([key,,kind])=>`<td>${dpFormat(r.current[key],kind)}${dpDelta(r.current[key],comparisonAvailable?r.previous[key]:null)}</td>`).join('')+'</tr>';
  }).join('')+(rows.length?'':`<tr><td colspan="${DP_PRODUCT_COLUMNS.length+2}">该区间没有店铺销售数据</td></tr>` )+'</tbody>';
}
function dpLoadCaptureLibrary() {
  if(window.html2canvas)return Promise.resolve(window.html2canvas);
  if(dpCaptureLibrary)return dpCaptureLibrary;
  dpCaptureLibrary=new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    const fail=()=>{clearTimeout(timeout);script.remove();reject(new Error('图片组件加载失败，请重试'));};
    const timeout=setTimeout(fail,20000);
    script.src='assets/vendor/html2canvas-1.4.1.min.js';script.async=true;
    script.onload=()=>{clearTimeout(timeout);if(window.html2canvas)resolve(window.html2canvas);else fail();};
    script.onerror=fail;document.head.append(script);
  }).catch(error=>{dpCaptureLibrary=null;throw error;});
  return dpCaptureLibrary;
}
// Copy the raw Chart.js configuration, retaining formatter functions without sharing mutable options.
function dpCopyChartConfig(value) {
  if(Array.isArray(value))return value.map(dpCopyChartConfig);
  if(value && Object.getPrototypeOf(value)===Object.prototype)
    return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,dpCopyChartConfig(item)]));
  return value;
}
async function dpDownloadImage() {
  if(dpExportBusy || !DAILY_REPORT_DATA)return;
  dpExportBusy=true;
  const button=dpEl('dp-download-image'),status=dpEl('dp-export-status');
  button.disabled=true;button.textContent='正在生成…';button.setAttribute('aria-busy','true');
  status.classList.remove('dp-export-error');status.textContent='正在生成完整日报，请稍候…';
  let clone=null,output=null;
  const exportCharts=[];
  try {
    const capture=await dpLoadCaptureLibrary();
    if(document.fonts)await document.fonts.ready;
    // Snapshot content and filters together; subsequent live filter changes cannot alter this export.
    const report=dpEl('daily-report-page'),start=state.start,end=state.end;
    const comparison=`${state.compareStart} 至 ${state.compareEnd}`,month=DP_STATE.salesMonth;
    const originals=[...report.querySelectorAll('canvas')];
    clone=report.cloneNode(true);clone.hidden=false;clone.className='dp-export';
    clone.setAttribute('aria-hidden','true');clone.inert=true;
    clone.querySelectorAll('.dp-export-actions,#dp-status,.dp-methods').forEach(el=>el.remove());
    const heading=document.createElement('header');heading.className='dp-export-heading';
    heading.innerHTML=`<h2>PH-SKINTIFIC · 日报</h2><p>查询日期：${dpEscape(start)} 至 ${dpEscape(end)}　｜　对比日期：${dpEscape(comparison)}　｜　概览月份：${dpEscape(month)}　｜　金额：人民币</p><div class="dp-legend"><span><i></i>本期</span><span><i class="dp-dashed"></i>对比期</span></div>`;
    clone.prepend(heading);
    clone.querySelectorAll('select').forEach(select=>{
      const text=document.createElement('strong');text.textContent=month;select.replaceWith(text);
    });
    clone.querySelectorAll('.dp-sort').forEach(sort=>{
      const text=document.createElement('span');text.textContent=sort.textContent;sort.replaceWith(text);
    });
    clone.querySelector('.dp-section-head .dp-muted')?.remove();
    document.body.append(clone);
    const width=Math.ceil(Math.max(2800,clone.querySelector('.dp-product-table').scrollWidth+64));
    clone.style.width=width+'px';
    // Render fresh charts at export dimensions. Live canvases, chart state and scroll remain untouched.
    const images=[...clone.querySelectorAll('canvas')].map((canvas,index)=>{
      const source=Chart.getChart(originals[index]);
      if(!source)throw new Error('趋势图尚未加载完成，请稍后重试');
      const box=canvas.parentElement.getBoundingClientRect();
      canvas.width=Math.ceil(box.width);canvas.height=Math.ceil(box.height);
      canvas.style.width=box.width+'px';canvas.style.height=box.height+'px';
      const chart=new Chart(canvas,{type:source.config.type,data:dpCopyChartConfig(source.config.data),
        options:{...dpCopyChartConfig(source.config.options),responsive:false,animation:false,events:[],devicePixelRatio:2}});
      exportCharts.push(chart);
      const image=new Image();image.alt=canvas.getAttribute('aria-label')||'趋势图';image.src=chart.toBase64Image();
      canvas.replaceWith(image);
      return image;
    });
    await Promise.all(images.map(image=>image.decode()));
    exportCharts.forEach(chart=>chart.destroy());exportCharts.length=0;
    const height=Math.ceil(clone.getBoundingClientRect().height);
    // Keep the PNG crisp while staying within browser canvas dimensions and a 24-megapixel budget.
    const scale=Math.min(2,32000/width,32000/height,Math.sqrt(24000000/(width*height)));
    output=await capture(clone,{backgroundColor:'#f4f7fb',scale,width,height,windowWidth:width,
      windowHeight:height,scrollX:0,scrollY:0,logging:false});
    const blob=await new Promise((resolve,reject)=>output.toBlob(value=>value?resolve(value):reject(new Error('图片生成失败，请重试')),'image/png'));
    const url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=`PH-SKINTIFIC-日报-${start}${end===start?'':'至'+end}.png`;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
    status.textContent='长图已下载';
  } catch(error) {
    console.error('日报长图导出失败',error);
    status.textContent='长图生成失败，请点击重试';status.classList.add('dp-export-error');
  } finally {
    exportCharts.forEach(chart=>chart.destroy());clone?.remove();
    if(output){output.width=0;output.height=0;}
    dpExportBusy=false;button.disabled=false;button.textContent='下载长图';button.removeAttribute('aria-busy');
  }
}
function dpRender() {
  const data=DAILY_REPORT_DATA,current=dpDates(state.start,state.end),previous=dpDates(state.compareStart,state.compareEnd);
  if(!dpDayCache)dpDayCache=dpStoreDays(facts);
  const byDay=dpDayCache,total=dpPeriod(current,byDay),compareTotal=dpPeriod(previous,byDay),buyers=dpBuyerPeriod(current,data.shop),compareBuyers=dpBuyerPeriod(previous,data.shop);
  const cutoff=SUBSIDY_DATA.monthly_rollup.at(-1)?.end??PAYLOAD.available_range.end;
  const channelByDay=new Map(SUBSIDY_DATA.daily.filter(r=>r.date<=cutoff).map(r=>[r.date,r]));
  dpEl('dp-status').innerHTML='';
  dpEl('dp-download-image').disabled=dpExportBusy;
  dpRenderOverview();
  const expenseKpis=[...DP_EXPENSE_METRICS.slice(0,2),['onsite-roi','站内 ROI','adROI','ratio'],...DP_EXPENSE_METRICS.slice(2),['offsite-roi','站外 ROI','metaROAS','ratio']];
  dpEl('dp-fee-kpis').innerHTML=expenseKpis.map(([,label,key,kind])=>dpMetricCard(label,total?.[key],compareTotal?.[key],kind)).join('');
  dpEl('dp-store-kpis').innerHTML=[['Sales￥','gmv','money'],['订单量','orders','number'],['点击量','clicks','number'],['点击率','clickRate','percent'],['转化率','conversion','percent']].map(([label,key,kind])=>dpMetricCard(label,total?.[key],compareTotal?.[key],kind)).join('')+dpMetricCard('新买家',buyers.newBuyers,compareBuyers.newBuyers,'number');
  dpRenderCharts(current,previous,byDay,channelByDay);
  dpRenderRecent(current,byDay,channelByDay,data.shop);
  dpRenderTop(current,previous,total,compareTotal);
  const sources=[['销售概览',SUBSIDY_DATA.sources.sales],['渠道日表',SUBSIDY_DATA.sources.daily],['店铺表现',PAYLOAD.source_urls.store],['新买家日表',data.sources.shop],['联盟明细',data.sources.affiliate]];
  dpEl('dp-sources').innerHTML=sources.filter(([,url])=>url).map(([label,url])=>`<a href="${dpEscape(url)}" target="_blank" rel="noopener">${label} ↗</a>`).join('');
}
function dpInitialize() {
  dpEl('dp-download-image').addEventListener('click',dpDownloadImage);
  dpEl('dp-sales-month').addEventListener('change',event=>{DP_STATE.salesMonth=event.target.value;dpRenderOverview();});
  dpEl('dp-top-products').addEventListener('click',event=>{
    const button=event.target.closest('[data-dp-sort]');if(!button)return;
    const key=button.dataset.dpSort;
    DP_STATE.sortDirection=DP_STATE.sortKey===key && DP_STATE.sortDirection==='desc'?'asc':'desc';DP_STATE.sortKey=key;
    const current=dpDates(state.start,state.end),previous=dpDates(state.compareStart,state.compareEnd);
    dpRenderTop(current,previous,dpPeriod(current,dpDayCache),dpPeriod(previous,dpDayCache));
  });
}
function renderDailyReportPage() {
  const actions=dpEl('daily-report-page').querySelector('.dp-export-actions');
  if(actions)document.querySelector('.dashboard-controls').append(actions);
  if(DAILY_REPORT_DATA){dpRender();return;}
  if(dpLoading)return;
  dpEl('dp-status').innerHTML='<div class="dp-loading">正在读取日报数据…</div>';
  dpLoading=fetch('assets/daily-report-data.json',{cache:'no-cache'}).then(response=>{if(!response.ok)throw new Error('HTTP '+response.status);return response.json();}).then(data=>{
    if(data.schema!==1||!data.shop||!data.affiliateCost)throw new Error('日报数据格式异常');
    DAILY_REPORT_DATA=data;dpInitialize();if(state.activePage==='daily-report')dpRender();
  }).catch(error=>{
    dpEl('dp-status').innerHTML=`<div class="dp-loading">日报加载失败：${dpEscape(error.message)} <button id="dp-retry" type="button">重试</button></div>`;
    dpEl('dp-retry').addEventListener('click',renderDailyReportPage);
  }).finally(()=>{dpLoading=null;});
}
if(location.hash==='#daily-report')state.activePage='daily-report';
