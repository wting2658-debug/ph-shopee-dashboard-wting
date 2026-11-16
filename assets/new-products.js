// ===== New products calculation helpers =====
const NP_METRICS = ['sales','units','orders','impressions','clicks','atc','atcUnits','onSpend','onGmv','onImpressions','onClicks','onOrders','metaSpend','metaGmv','metaImpressions','metaClicks','metaOrders','ttQty','shopeeQty','lazadaQty'];
const npRatio = (a,b) => a == null || b == null || !b ? null : a/b;
const NP_TREND_METRICS = [
  {key:'sales',label:'Sales',kind:'money',color:'#2d83c5'},
  {key:'orders',label:'订单数',kind:'number',color:'#cf6742'},
  {key:'impressions',label:'曝光',kind:'number',color:'#7b79b7'},
  {key:'clicks',label:'点击',kind:'number',color:'#b69b30'},
  {key:'ctr',label:'CTR',kind:'percent',color:'#a764a6'},
  {key:'cvr',label:'转化率',kind:'percent',color:'#418da1'},
  {key:'onGmv',label:'站内Sales',kind:'money',color:'#475dc7'},
  {key:'onSpend',label:'站内花费',kind:'money',color:'#ef9a4c'},
  {key:'onFee',label:'站内费比',kind:'percent',color:'#bc5358'},
  {key:'onRoi',label:'站内ROI',kind:'ratio',color:'#8d6cb0'},
  {key:'metaGmv',label:'站外Sales',kind:'money',color:'#287d64'},
  {key:'metaSpend',label:'站外花费',kind:'money',color:'#37a58d'},
  {key:'metaFee',label:'站外费比',kind:'percent',color:'#905c3a'},
  {key:'metaRoi',label:'站外ROI',kind:'ratio',color:'#667b3a'}
];
const NP_TREND_DEFAULT = ['sales','onSpend','metaSpend'];
function npTrendValue(row,key) {
  switch (key) {
    case 'ctr': return npRatio(row.clicks,row.impressions);
    case 'cvr': return npRatio(row.orders,row.clicks);
    case 'onFee': return npRatio(row.onSpend,row.sales);
    case 'metaFee': return npRatio(row.metaSpend,row.sales);
    case 'onRoi': return npRatio(row.onGmv,row.onSpend);
    case 'metaRoi': return npRatio(row.metaGmv,row.metaSpend);
    default: return row[key]??null;
  }
}
function npShipmentTotals(row) {
  return {
    gap:row.ttQty!=null && row.shopeeQty!=null?row.ttQty-row.shopeeQty:null,
    total:['ttQty','shopeeQty','lazadaQty'].every(key=>row[key]!=null)?row.ttQty+row.shopeeQty+row.lazadaQty:null
  };
}
function npDates(start,end) {
  const out=[],d=new Date(`${start}T00:00:00Z`),last=new Date(`${end}T00:00:00Z`);
  while (Number.isFinite(+d) && d<=last) { out.push(d.toISOString().slice(0,10)); d.setUTCDate(d.getUTCDate()+1); }
  return out;
}
function npWindow(product,filters,data) {
  let start=product.launch,end=data.coverage.performance.end || data.cutoff;
  if (filters.mode==='year' || filters.mode==='month') {
    const y=Number(filters.year),m=filters.mode==='month'?Number(filters.month):1;
    const first=`${y}-${String(m).padStart(2,'0')}-01`;
    const last=new Date(Date.UTC(filters.mode==='year'?y+1:(m===12?y+1:y),filters.mode==='year'?0:(m===12?0:m),0)).toISOString().slice(0,10);
    start=start>first?start:first; end=end<last?end:last;
  }
  return {start,end};
}
function npAggregate(product,start,end) {
  const dates=npDates(start,end),map=new Map(product.rows.map(r=>[r.date,r]));
  const rows=dates.map(d=>map.get(d)||{date:d}),out={start,end,days:dates.length,rows,counts:{}};
  for (const key of NP_METRICS) {
    const known=rows.filter(r=>r[key]!=null);
    out.counts[key]=known.length;
    out[key]=known.length?known.reduce((a,r)=>a+r[key],0):null;
  }
  const rate=(a,b,complete=false)=> {
    if (complete && (out.counts[a]!==out.days || out.counts[b]!==out.days)) return null;
    if (rows.some(r=>(r[a]!=null)!==(r[b]!=null))) return null;
    return npRatio(out[a],out[b]);
  };
  out.ctr=rate('clicks','impressions'); out.cvr=rate('orders','clicks');
  out.onRoi=rate('onGmv','onSpend',true); out.metaRoi=rate('metaGmv','metaSpend',true);
  out.totalSpend=out.onSpend!=null && out.metaSpend!=null?out.onSpend+out.metaSpend:null;
  out.counts.totalSpend=Math.min(out.counts.onSpend,out.counts.metaSpend);
  out.fullRoi=out.days && ['sales','onSpend','metaSpend'].every(k=>out.counts[k]===out.days)?npRatio(out.sales,out.totalSpend):null;
  return out;
}
function npMatches(product,filters) {
  const query=(filters.search||'').trim().toLowerCase();
  return (!filters.launchYear || product.launch.slice(0,4)===filters.launchYear) && (!filters.launchMonth || product.launch.slice(5,7)===filters.launchMonth) && (!query || `${product.id} ${product.name}`.toLowerCase().includes(query));
}
// ===== End new products calculation helpers =====

let NEW_PRODUCTS_DATA=null,newProductsLoading=null;
const NP_STATE={launchYear:'',launchMonth:'',mode:'cumulative',year:'',month:'',search:'',sort:'launch',product:'',detail:'sales',page:0,trendMetrics:[...NP_TREND_DEFAULT]};
const NP_CHARTS=new Map();
const npEl=id=>document.getElementById(id);
const npEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const npNum=(value,digits=0)=>value==null || !Number.isFinite(value)?'—':value.toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits});
const npMoney=value=>value==null?'—':`¥${npNum(value)}`;
const npPercent=value=>value==null?'—':`${npNum(value*100,2)}%`;
const npRoi=value=>value==null?'—':`${npNum(value,2)}`;
const npOption=(value,label)=>`<option value="${npEscape(value)}">${npEscape(label)}</option>`;
function npMetric(aggregate,key,kind='number') {
  const value=aggregate[key],format=kind==='money'?npMoney:kind==='decimal'?(v=>npNum(v,2)):npNum;
  const count=aggregate.counts[key],partial=value!=null && count<aggregate.days;
  return `<span${partial?` title="已覆盖 ${count} / ${aggregate.days} 天，显示已覆盖日期合计"`:''}>${format(value)}${partial?'*':''}</span>`;
}
function npProductCell(p) {
  return `<button type="button" class="np-link" data-np-product="${npEscape(p.id)}">${npEscape(p.name)}</button><small>${npEscape(p.id)}</small>${p.launch>NEW_PRODUCTS_DATA.generatedAt.slice(0,10)?'<span class="np-tag">待上新</span>':p.launch>NEW_PRODUCTS_DATA.coverage.performance.end?'<span class="np-tag">尚无上新后数据</span>':''}`;
}
function npNoRows(columns) { return `<tr><td colspan="${columns}" class="np-empty">当前筛选下没有新品链接，请调整年份、月份或搜索条件。</td></tr>`; }
function npVisible() {
  return NEW_PRODUCTS_DATA.products.filter(p=>npMatches(p,NP_STATE)).map(p=>({p,pre:npAggregate(p,p.preStart,p.preEnd),post:npAggregate(p,...Object.values(npWindow(p,NP_STATE,NEW_PRODUCTS_DATA)))})).sort((a,b)=>NP_STATE.sort==='sales'?(b.post.sales??-1)-(a.post.sales??-1):NP_STATE.sort==='spend'?(b.post.totalSpend??-1)-(a.post.totalSpend??-1):b.p.launch.localeCompare(a.p.launch));
}
function npInitialize() {
  const years=[...new Set(NEW_PRODUCTS_DATA.products.map(p=>p.launch.slice(0,4)))].sort().reverse();
  const statsYears=[...new Set(NEW_PRODUCTS_DATA.coverage.performance.dates.map(d=>d.slice(0,4)))].sort().reverse();
  const latest=NEW_PRODUCTS_DATA.coverage.performance.end;
  NP_STATE.launchYear=years.includes(latest.slice(0,4))?latest.slice(0,4):years[0];
  NP_STATE.year=latest.slice(0,4); NP_STATE.month=latest.slice(5,7);
  npEl('np-launch-year').innerHTML=npOption('','全部年份')+years.map(y=>npOption(y,`${y} 年`)).join('');
  npEl('np-launch-month').innerHTML=npOption('','全部月份')+Array.from({length:12},(_,i)=>npOption(String(i+1).padStart(2,'0'),`${i+1} 月`)).join('');
  npEl('np-year').innerHTML=statsYears.map(y=>npOption(y,`${y} 年`)).join('');
  npEl('np-month').innerHTML=Array.from({length:12},(_,i)=>npOption(String(i+1).padStart(2,'0'),`${i+1} 月`)).join('');
  npEl('np-trend-controls').innerHTML=NP_TREND_METRICS.map(metric=>`<button type="button" data-np-trend-metric="${metric.key}" aria-pressed="false"><span class="np-metric-dot" aria-hidden="true" style="background:${metric.color}"></span>${metric.label}</button>`).join('');
  const controls={'np-launch-year':'launchYear','np-launch-month':'launchMonth','np-mode':'mode','np-year':'year','np-month':'month','np-sort':'sort','np-search':'search'};
  for (const [id,key] of Object.entries(controls)) {
    npEl(id).value=NP_STATE[key];
    npEl(id).addEventListener(id==='np-search'?'input':'change',e=>{NP_STATE[key]=e.target.value; NP_STATE.page=0;npRender();});
  }
  npEl('np-reset').addEventListener('click',()=>{
    Object.assign(NP_STATE,{launchYear:latest.slice(0,4),launchMonth:'',mode:'cumulative',year:latest.slice(0,4),month:latest.slice(5,7),search:'',sort:'launch',product:'',page:0,trendMetrics:[...NP_TREND_DEFAULT]});
    for (const [id,key] of Object.entries(controls)) npEl(id).value=NP_STATE[key];
    npRender();
  });
  npEl('new-products-page').addEventListener('click',e=>{
    const link=e.target.closest('[data-np-product]');
    const preRow=e.target.closest('[data-np-pre-product]');
    if (link || preRow) {
      NP_STATE.product=link?.dataset.npProduct||preRow.dataset.npPreProduct;NP_STATE.page=0;npRender();
      npEl(preRow?'np-pre-trend-panel':'np-detail-panel').scrollIntoView({behavior:'smooth',block:preRow?'nearest':'start'});
    }
    const detail=e.target.closest('[data-np-detail]');
    if (detail) { NP_STATE.detail=detail.dataset.npDetail;NP_STATE.page=0;npRenderDetail(npVisible()); }
    const metric=e.target.closest('[data-np-trend-metric]');
    if (metric) npToggleTrendMetric(metric.dataset.npTrendMetric);
  });
  npEl('np-product').addEventListener('change',e=>{NP_STATE.product=e.target.value;NP_STATE.page=0;npRender();});
  npEl('np-prev').addEventListener('click',()=>{NP_STATE.page--;npRenderDetail(npVisible());});
  npEl('np-next').addEventListener('click',()=>{NP_STATE.page++;npRenderDetail(npVisible());});
  const labels={mapping:'链接与上新时间',performance:'商品日表现',onsite:'站内投放',meta:'Meta 投放',shipment:'TT / 虾皮 / Lazada 出货'};
  npEl('np-sources').innerHTML='<div class="np-source-links">'+Object.entries(NEW_PRODUCTS_DATA.sources).map(([key,url])=>`<a href="${npEscape(url)}" target="_blank" rel="noopener">${labels[key]}</a>`).join('')+'</div>';
  const issues=NEW_PRODUCTS_DATA.issues.filter(i=>i.fields.some(f=>f!=='missing_product_total'));
  npEl('np-quality').textContent=`${NEW_PRODUCTS_DATA.undatedLinks} 个链接未填写上新日期，未纳入清单。${issues.length?`源表有 ${issues.length} 个链接日的重复汇总行存在字段冲突，冲突值显示“—”：${issues.map(i=>`${i.id}（${i.date}）`).join('、')}。`:''}`;
}
function npRender() {
  const data=NEW_PRODUCTS_DATA,visible=npVisible(),latest=data.coverage.performance.end;
  npEl('np-year-field').hidden=NP_STATE.mode==='cumulative';
  npEl('np-month-field').hidden=NP_STATE.mode!=='month';
  const modeLabel=NP_STATE.mode==='cumulative'?`各链接上新日起累计至 ${latest}`:NP_STATE.mode==='year'?`${NP_STATE.year} 年（仅统计上新后）`:`${NP_STATE.year}-${NP_STATE.month}（仅统计上新后）`;
  npEl('np-period').textContent=`${visible.length} 个新品链接 · ${modeLabel} · 数据更新 ${data.generatedAt.slice(0,16).replace('T',' ')}`;
  npEl('np-sales-caption').textContent=`当前统计：${modeLabel}。共用 SKU 的链接出货量不可相加。带 * 的值为部分日期合计。`;
  npEl('np-status').textContent='';
  if (!visible.some(x=>x.p.id===NP_STATE.product)) NP_STATE.product=visible.find(x=>x.p.launch<=latest)?.p.id||visible[0]?.p.id||'';
  const tr=(p,cells,pre=false)=>`<tr class="${p.id===NP_STATE.product?'np-selected':''}"${pre?` data-np-pre-product="${npEscape(p.id)}"`:''}><td>${npProductCell(p)}</td>${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`;
  npEl('np-pre-rows').innerHTML=visible.map(({p,pre})=>tr(p,[p.launch,`<span class="np-date-cell">${p.preStart}<br>至 ${p.preEnd}</span>`,npMetric(pre,'sales','money'),npMetric(pre,'impressions'),npMetric(pre,'clicks'),npPercent(pre.ctr),npMetric(pre,'atc'),`${pre.counts.impressions} / 7 天${pre.counts.impressions===0?'<small>数据未覆盖</small>':''}`],true)).join('')||npNoRows(9);
  npEl('np-sales-rows').innerHTML=visible.map(({p,post:a})=>tr(p,[a.days?`<span class="np-date-cell">${a.start}<br>至 ${a.end}</span>`:'未进入统计期',npMetric(a,'sales','money'),npMetric(a,'units'),`${npMetric(a,'shopeeQty')}${p.sharedSkus.length?'<small>含共用 SKU</small>':''}`,npMetric(a,'impressions'),npMetric(a,'clicks'),npPercent(a.ctr),npPercent(a.cvr)])).join('')||npNoRows(9);
  npEl('np-ads-rows').innerHTML=visible.map(({p,post:a})=>tr(p,[npMetric(a,'onSpend','money'),npMetric(a,'onGmv','money'),npRoi(a.onRoi),npMetric(a,'metaSpend','money'),npMetric(a,'metaGmv','money'),npRoi(a.metaRoi),npMetric(a,'totalSpend','money'),npRoi(a.fullRoi),a.days?`<small>站内 ${a.counts.onSpend}/${a.days} 天<br>Meta ${a.counts.metaSpend}/${a.days} 天</small>`:'—'])).join('')||npNoRows(10);
  npEl('np-product').innerHTML=visible.map(({p})=>npOption(p.id,`${p.name} · ${p.id}`)).join('');
  npEl('np-product').value=NP_STATE.product;
  npRenderPreTrend(visible);
  npRenderDetail(visible);
}
function npChart(id,labels,datasets,money=false,percentAxis=false) {
  if (NP_CHARTS.has(id)) {NP_CHARTS.get(id).destroy();NP_CHARTS.delete(id);}
  if (typeof Chart==='undefined') return;
  const colors=['#2d83c5','#ef9a4c','#37a58d','#8b73d0'];
  const config={
    type:'line',
    data:{labels,datasets:datasets.map((d,i)=>({...d,borderColor:colors[i],backgroundColor:colors[i],borderWidth:2,pointRadius:labels.length>60?0:2,tension:.18,spanGaps:false}))},
    options:{
      responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'top',labels:{boxWidth:12,font:{size:12}}},tooltip:{callbacks:{label:c=>`${c.dataset.label}：${c.dataset.yAxisID==='yCtr'?npPercent(c.raw):money?npMoney(c.raw):npNum(c.raw)}`}}},
      scales:{x:{grid:{display:false},ticks:{maxTicksLimit:9,font:{size:11}}},y:{beginAtZero:true,ticks:{callback:v=>money?`¥${npNum(v)}`:npNum(v),font:{size:11}}}}
    }
  };
  if (percentAxis) {
    config.options.scales.y.title={display:true,text:'曝光 / 点击 / 加购人数',font:{size:11}};
    config.options.scales.yCtr={type:'linear',position:'right',beginAtZero:true,grid:{drawOnChartArea:false},title:{display:true,text:'点击率',font:{size:11}},ticks:{callback:v=>npPercent(v),font:{size:11}}};
  }
  NP_CHARTS.set(id,new Chart(npEl(id),config));
}
function npRenderPreTrend(visible) {
  const selected=visible.find(x=>x.p.id===NP_STATE.product);
  npEl('np-pre-trend-panel').hidden=!selected;
  if (!selected) {
    if (NP_CHARTS.has('np-pre-chart')) {NP_CHARTS.get('np-pre-chart').destroy();NP_CHARTS.delete('np-pre-chart');}
    return;
  }
  const {p,pre}=selected,rows=pre.rows;
  npEl('np-pre-trend-caption').textContent=`${p.name} · ${p.id} · ${p.preStart} 至 ${p.preEnd}（上新日期 ${p.launch}）`;
  const counts=['impressions','clicks','atc'].map(key=>pre.counts[key]);
  const coverage=counts.every(count=>count===0)?'该链接上新前 7 天暂无数据。':counts.some(count=>count<7)?'部分日期数据未覆盖，曲线断开显示，不计为 0。':'';
  npEl('np-pre-trend-note').textContent=`左轴：曝光、点击、加购人数；右轴：点击率（当日点击 ÷ 当日曝光）。点击图例可隐藏或显示指标。${coverage}`;
  npChart('np-pre-chart',rows.map(r=>r.date),[
    {label:'曝光',data:rows.map(r=>r.impressions??null)},
    {label:'点击',data:rows.map(r=>r.clicks??null)},
    {label:'加购人数',data:rows.map(r=>r.atc??null)},
    {label:'点击率',yAxisID:'yCtr',borderDash:[5,4],data:rows.map(r=>npRatio(r.clicks,r.impressions))}
  ],false,true);
}
function npToggleTrendMetric(key) {
  NP_STATE.trendMetrics=NP_STATE.trendMetrics.includes(key)?NP_STATE.trendMetrics.filter(value=>value!==key):[...NP_STATE.trendMetrics,key];
  npRenderTrend(npVisible().find(x=>x.p.id===NP_STATE.product)?.post.rows||[]);
}
function npRenderTrend(rows) {
  const selected=NP_TREND_METRICS.filter(metric=>NP_STATE.trendMetrics.includes(metric.key));
  for (const button of npEl('np-trend-controls').querySelectorAll('button')) {
    const active=NP_STATE.trendMetrics.includes(button.dataset.npTrendMetric);
    button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));
  }
  npEl('np-trend-selected').textContent=selected.length?`已选：${selected.map(metric=>metric.label).join('、')}。点击指标按钮可多选曲线，再次点击取消。`:'点击右侧指标按钮，选择要查看的趋势。';
  npEl('np-trend-empty').hidden=selected.length>0;
  npEl('np-trend-chart-wrap').hidden=selected.length===0;
  if (NP_CHARTS.has('np-sales-chart')) {NP_CHARTS.get('np-sales-chart').destroy();NP_CHARTS.delete('np-sales-chart');}
  if (!selected.length || typeof Chart==='undefined') return;
  const format={money:npMoney,number:npNum,percent:npPercent,ratio:value=>value==null?'—':`${npRoi(value)}×`};
  const axisLabel={money:'金额（¥）',number:'数量',percent:'百分比',ratio:'ROI（倍）'};
  const kinds=['money','number','percent','ratio'].filter(kind=>selected.some(metric=>metric.kind===kind));
  const scales={x:{grid:{display:false},ticks:{maxTicksLimit:9,font:{size:11}}}};
  kinds.forEach((kind,index)=>{
    scales[`y_${kind}`]={axis:'y',type:'linear',position:kind==='money'||kind==='number'?'left':'right',beginAtZero:true,
      grid:{drawOnChartArea:index===0},title:{display:true,text:axisLabel[kind],font:{size:11}},ticks:{callback:value=>format[kind](value),font:{size:11}}};
  });
  NP_CHARTS.set('np-sales-chart',new Chart(npEl('np-sales-chart'),{
    type:'line',
    data:{labels:rows.map(row=>row.date),datasets:selected.map(metric=>({
      label:metric.label,metricKind:metric.kind,yAxisID:`y_${metric.kind}`,data:rows.map(row=>npTrendValue(row,metric.key)),
      borderColor:metric.color,backgroundColor:metric.color,borderWidth:2,pointRadius:rows.length>60?0:2,tension:.18,spanGaps:false,
      borderDash:metric.kind==='percent'?[5,4]:metric.kind==='ratio'?[2,3]:[]
    }))},
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},scales,
      plugins:{legend:{position:'top',labels:{boxWidth:12,font:{size:12}},onClick:(_event,item)=>npToggleTrendMetric(selected[item.datasetIndex].key)},tooltip:{callbacks:{label:context=>`${context.dataset.label}：${format[context.dataset.metricKind](context.raw)}`}}}}
  }));
}
function npDailyColumns(detail) {
  if (detail==='onsite') return [['日期',r=>r.date],['站内花费（¥）',r=>npMoney(r.onSpend)],['站内广告 GMV（¥）',r=>npMoney(r.onGmv)],['ROI',r=>npRoi(npRatio(r.onGmv,r.onSpend))],['曝光',r=>npNum(r.onImpressions)],['点击',r=>npNum(r.onClicks)],['点击率',r=>npPercent(npRatio(r.onClicks,r.onImpressions))],['订单数',r=>npNum(r.onOrders)],['CPC（¥）',r=>r.onSpend==null?'—':`¥${npNum(npRatio(r.onSpend,r.onClicks),2)}`],['CVR',r=>npPercent(npRatio(r.onOrders,r.onClicks))]];
  if (detail==='meta') return [['日期',r=>r.date],['Meta 花费（¥）',r=>npMoney(r.metaSpend)],['转化价值（¥）',r=>npMoney(r.metaGmv)],['ROI',r=>npRoi(npRatio(r.metaGmv,r.metaSpend))],['曝光',r=>npNum(r.metaImpressions)],['点击',r=>npNum(r.metaClicks)],['CTR',r=>npPercent(npRatio(r.metaClicks,r.metaImpressions))],['购物次数',r=>npNum(r.metaOrders)],['CPM（¥）',r=>npNum(npRatio(r.metaSpend==null?null:r.metaSpend*1000,r.metaImpressions),2)],['CVR',r=>npPercent(npRatio(r.metaOrders,r.metaClicks))]];
  if (detail==='shipment') return [['日期',r=>r.date],['TT出货件数',r=>npNum(r.ttQty)],['虾皮出货件数',r=>npNum(r.shopeeQty)],['Lazada出货件数',r=>npNum(r.lazadaQty)],['TT&虾皮gap',r=>npNum(npShipmentTotals(r).gap)],['总出货',r=>npNum(npShipmentTotals(r).total)]];
  return [['日期',r=>r.date],['Sales（¥）',r=>npMoney(r.sales)],['售出件数',r=>npNum(r.units)],['订单数',r=>npNum(r.orders)],['曝光',r=>npNum(r.impressions)],['点击',r=>npNum(r.clicks)],['CTR',r=>npPercent(npRatio(r.clicks,r.impressions))],['成交转化率',r=>npPercent(npRatio(r.orders,r.clicks))],['加购人数',r=>npNum(r.atc)],['加购件数',r=>npNum(r.atcUnits)]];
}
function npRenderDetail(visible) {
  const selected=visible.find(x=>x.p.id===NP_STATE.product),p=selected?.p;
  npEl('np-detail-panel').hidden=!p;
  if (!p) {for(const chart of NP_CHARTS.values())chart.destroy();NP_CHARTS.clear();return;}
  const a=selected.post,rows=a.rows;
  npEl('np-detail-caption').textContent=`${p.name} · ${p.id} · ${a.days?`${a.start} 至 ${a.end}`:'尚未进入统计期'}`;
  const skuSummary=p.shipmentSkus.length?`关联 ${p.shipmentSkus.length} 个有 TT / 虾皮 / Lazada 出货记录的 SKU${p.sharedSkus.length?`，其中 ${p.sharedSkus.length} 个被多个链接共用，出货数据为 SKU 口径，不能认作该链接独占出货`:''}`:'未找到可精确匹配的出货 SKU，出货数据显示“—”';
  npEl('np-detail-info').innerHTML=`上新日期 ${p.launch} · ${p.url?`<a href="${npEscape(p.url)}" target="_blank" rel="noopener">打开商品链接</a>`:'源表未提供商品链接'}<br>${npEscape(skuSummary)}。<br>Meta 关联：${npEscape(p.metaAmbiguous?'名称对应多个 Product ID，未分摊':p.metaNames.join('、')||'未匹配到对应投放记录，花费与 ROI 保留“—”')}。${p.shipmentSkus.length?`<details><summary>查看关联 SKU</summary>${npEscape(p.shipmentSkus.join('、'))}</details>`:''}`;
  npRenderTrend(rows);
  npEl('np-daily-head').closest('table').classList.toggle('np-shipment-table',NP_STATE.detail==='shipment');
  npEl('np-shipment-caption').hidden=NP_STATE.detail!=='shipment';
  for (const button of npEl('new-products-page').querySelectorAll('[data-np-detail]')) button.classList.toggle('active',button.dataset.npDetail===NP_STATE.detail);
  const cols=npDailyColumns(NP_STATE.detail),reversed=[...rows].reverse(),pages=Math.max(1,Math.ceil(rows.length/15));
  NP_STATE.page=Math.max(0,Math.min(NP_STATE.page,pages-1));
  npEl('np-daily-head').innerHTML='<tr>'+cols.map(([label])=>`<th>${label}</th>`).join('')+'</tr>';
  npEl('np-daily-rows').innerHTML=reversed.slice(NP_STATE.page*15,(NP_STATE.page+1)*15).map(r=>'<tr>'+cols.map(([,format])=>`<td>${format(r)}</td>`).join('')+'</tr>').join('')||`<tr><td colspan="${cols.length}" class="np-empty">所选统计期没有上新后数据。</td></tr>`;
  npEl('np-daily-count').textContent=`共 ${rows.length} 天 · 第 ${NP_STATE.page+1} / ${pages} 页`;
  npEl('np-prev').disabled=NP_STATE.page===0;npEl('np-next').disabled=NP_STATE.page>=pages-1;
}
function renderNewProductsPage() {
  if (NEW_PRODUCTS_DATA) {npRender();return;}
  if (newProductsLoading) return;
  npEl('np-status').innerHTML='<div class="np-warning">正在读取新品链接、商品日表现与投放出货数据…</div>';
  newProductsLoading=fetch('assets/new-products-data.json',{cache:'no-cache'}).then(response=>{if(!response.ok)throw new Error(`HTTP ${response.status}`);return response.json();}).then(data=>{NEW_PRODUCTS_DATA=data;npInitialize();if(state.activePage==='new-products')npRender();}).catch(error=>{
    npEl('np-status').innerHTML=`<div class="np-warning">新品数据加载失败：${npEscape(error.message)}。<button id="np-retry" class="np-button" type="button">重试</button></div>`;
    npEl('np-retry').addEventListener('click',renderNewProductsPage);
  }).finally(()=>{newProductsLoading=null;});
}
if (location.hash==='#new-products') state.activePage='new-products';
