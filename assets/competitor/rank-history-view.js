'use strict';
// This view shares the dashboard metric and language; its period and category set are independent.
const historyCategories=categoryTree.categories;
const historyYears=unique(months.map(m=>m.slice(0,4))).reverse();
const historyShops=new Map(RankHistory.shops(all).map(s=>[s.key,s]));
const historyDefaultShop=historyShops.has('https://shopee.ph/skintific.ph')?'https://shopee.ph/skintific.ph':[...historyShops.values()].find(s=>s.own)?.key;
let historyState=null;
const ht=(cn,en)=>english?en:cn;
const hm=m=>english?m:m.slice(5).replace(/^0/,'')+'月';
const hr=n=>english?'#'+n:'第'+n+'名';
function initHistory(){
  if(historyState)return;
  const selectedCategory=cat(),initial=[selectedCategory];
  if(selectedCategory==='Beauty >> Skincare')initial.push('Beauty >> Skincare >> Face Sunscreen');
  else if(selectedCategory.split(' >> ').length===3)initial.unshift(selectedCategory.split(' >> ').slice(0,2).join(' >> '));
  historyState={year:months[0]?.slice(0,4)||String(new Date().getFullYear()),end:months[0]?.slice(5)||'12',defaultCategories:[...initial],shops:new Set(historyDefaultShop?[historyDefaultShop]:[]),shopOpen:false,categories:new Set(initial),query:'',pages:{shop:1,product:1},categoryOpen:false};
}
function historyMonths(){return Array.from({length:Number(historyState.end)},(_,i)=>historyState.year+'-'+String(i+1).padStart(2,'0'));}
function historyShopSummary(){
  const chosen=[...historyState.shops];
  if(chosen.length===1){const s=historyShops.get(chosen[0]);return s.name+' · '+(s.id?'ID: '+s.id:ht('ID 暂缺','ID unavailable'));}
  return chosen.length?ht('已选 '+chosen.length+' / '+historyShops.size+' 家店铺','Selected '+chosen.length+' / '+historyShops.size+' shops'):ht('请选择店铺','Select shops');
}
function historyShopOptions(){
  const q=historyState.query.trim().toLowerCase();
  const stores=[...historyShops.values()].filter(s=>!q||(s.name+' '+s.brand+' '+s.key+' '+s.id).toLowerCase().includes(q));
  return stores.length?stores.map(s=>`<label class="shop-choice"><input type="checkbox" data-history-shop="${esc(s.key)}" ${historyState.shops.has(s.key)?'checked':''}><span><strong>${esc(s.name)}</strong><small>${s.id?'ID: '+esc(s.id):ht('ID 暂缺','ID unavailable')+' · '+esc(s.key.split('/').at(-1))}</small></span></label>`).join(''):`<p class="shop-no-results">${ht('没有匹配的店铺，请更换名称或 ID。','No shops match. Try another name or ID.')}</p>`;
}
function historyShopFilter(){
  return `<div class="history-shop-filter"><span class="filter-label">${ht('品牌／店铺','Brand / Shop')}</span><details id="history-shop-picker" ${historyState.shopOpen?'open':''}><summary aria-label="${ht('筛选品牌或店铺','Filter brands or shops')}"><span>${esc(historyShopSummary())}</span><span class="shop-chevron" aria-hidden="true">⌄</span></summary><div class="shop-popover"><div class="shop-actions"><button type="button" data-history-shops="default">${ht('恢复默认','Restore defaults')}</button><button type="button" data-history-shops="all">${ht('全选','Select all')}</button><button type="button" data-history-shops="none">${ht('清空','Clear')}</button><button type="button" data-history-shops="done">${ht('完成','Done')}</button></div><div class="shop-search"><input id="history-shop-search" type="search" value="${esc(historyState.query)}" placeholder="${ht('搜索店铺名称 / 店铺 ID','Search shop name / shop ID')}" aria-label="${ht('搜索店铺名称或店铺ID','Search shop name or shop ID')}"></div><div id="history-shop-list" class="shop-options" role="group" aria-label="${ht('店铺多选列表','Shop selection list')}">${historyShopOptions()}</div><div class="shop-selection-count" role="status">${ht('已选','Selected')} ${historyState.shops.size} / ${historyShops.size} ${ht('家店铺','shops')}</div></div></details></div>`;
}
function sizeHistoryShopMenu(){
  const picker=$('history-shop-picker');if(!picker?.open)return;
  const rect=picker.getBoundingClientRect(),below=innerHeight-rect.bottom,above=rect.top;
  const upwards=below<240&&above>below;
  picker.classList.toggle('opens-up',upwards);
  picker.style.setProperty('--shop-menu-height',Math.max(180,Math.min(560,(upwards?above:below)-16))+'px');
}
function closeHistoryShopMenu(focus=false){
  const picker=$('history-shop-picker');if(!picker)return;
  picker.open=false;historyState.shopOpen=false;
  if(focus)picker.querySelector('summary').focus();
}
function historyFilters(){
  const state=historyState,max=months.filter(m=>m.startsWith(state.year)).sort().at(-1)?.slice(5)||'12';
  return `<div class="history-filters"><label>${ht('年度','Year')}<select id="history-year">${historyYears.map(y=>`<option ${y===state.year?'selected':''}>${y}</option>`).join('')}</select></label><label>${ht('统计截至（月）','Through month')}<select id="history-end">${Array.from({length:Number(max)},(_,i)=>String(i+1).padStart(2,'0')).map(m=>`<option value="${m}" ${m===state.end?'selected':''}>${hm(state.year+'-'+m)}</option>`).join('')}</select></label>${historyShopFilter()}${CategoryPicker.render({id:'history-category',label:ht('排名类目（可多选）','Ranking categories (multiple)'),tree:categoryTree,selected:state.categories,multiple:true,en:english,open:state.categoryOpen,extraClass:'history-category-filter'})}</div>`;
}
function historyEntity(g,compact=false){
  const r=g.sample,product=g.kind==='product';
  return `<div class="entity ${compact?'history-compact':''}">${image(r)}<div>${link(product?r.product_url:r.shop_url,product?r.product_name:r.shop_name||r.brand)}${product?`<div class="sub">${link(r.shop_url,r.shop_name)} · ID ${esc(g.id)}</div>`:`<div class="sub">${esc(g.id.split('/').at(-1))}</div>`}${!compact&&product?`<div class="sub">${ht('类型','Type')}：${esc(type(r))}${r.category.split(' >> ').length<3?ht('（名称推断）',' (inferred from name)'):''}</div>`:''}</div></div>`;
}
function trendEvidence(g){
  const a=g.analysis;if(!a.count)return ht('没有公开的有效名次','No published ranks');
  return `${hm(a.first.month)} ${hr(a.first.rank)} → ${hm(a.last.month)} ${hr(a.last.rank)}${a.delta?`${ht('，',', ')}${a.delta>0?ht('提升','up'):ht('下降','down')} ${Math.abs(a.delta)} ${ht('位','places')}`:ht('，首末持平',', unchanged endpoints')} · ${a.count} ${ht('个有效月','ranked months')}${a.front!=null?`<span class="sub history-evidence-average">${ht('前段／后段平均名次','Early / late average rank')} ${a.front.toFixed(1)} / ${a.back.toFixed(1)}</span>`:''}`;
}
function historyTrend(groups){
  const statuses=['up','down','stable','mixed','insufficient','missing','unknown'];
  const buckets=Object.fromEntries(statuses.map(status=>[status,groups.filter(g=>g.analysis.status===status)]));
  function list(status,label){const list=buckets[status];return `<div class="trend-group"><strong class="${status==='up'?'up':'down'}">${label} · ${list.length}</strong><div>${list.length?list.slice(0,4).map(trendItem).join('')+(list.length>4?`<details class="trend-more"><summary>${ht('展开其余','Show remaining')} ${list.length-4} ${ht('项','records')}</summary>${list.slice(4).map(trendItem).join('')}</details>`:''):`<p>${ht('暂无明确趋势','No clear trend')}</p>`}</div></div>`;}
  function trendItem(g){return `<div class="trend-item">${historyEntity(g,true)}<div class="sub">${esc(g.category.replaceAll(' >> ',' / '))}</div><p class="${g.analysis.status==='up'?'up':'down'}">${trendEvidence(g)}</p></div>`;}
  const otherLabels={stable:ht('有效月排名保持不变。','Ranks are unchanged across ranked months.'),mixed:ht('首末变化、整体走势与前后段平均方向未一致，暂不判单向趋势。','Endpoint change, the overall trend and early / late averages do not agree; no single direction is assigned.'),insufficient:ht('不足3个有效月，仅列出已取得的名次，待观察。','Fewer than 3 ranked months; more observations are needed.'),missing:ht('截至月名次缺失，仅展示历史名次，不判当前升降。','The final month has no published rank; historical ranks alone do not establish a current direction.'),unknown:ht('返回的记录均未公开具体名次，无法判断排名走势。','Returned records contain no published ranks; direction cannot be assessed.')};
  const others=groups.filter(g=>otherLabels[g.analysis.status]);
  const otherDetails=others.length?`<details class="trend-other" ${groups.length<=4&&!buckets.up.length&&!buckets.down.length?'open':''}><summary>${ht('其他记录的具体分析','Analysis of other records')} · ${others.length}</summary>${others.map(g=>`<div class="trend-item">${historyEntity(g,true)}<div class="sub">${esc(g.category.replaceAll(' >> ',' / '))}</div><p>${trendEvidence(g)}</p><p class="history-method">${otherLabels[g.analysis.status]}</p></div>`).join('')}</details>`:'';
  return `<article class="trend-card"><div class="history-section-title"><h3>${ht('年度趋势结论','Yearly trend analysis')}</h3><span>${esc(historyState.year)}-01 — ${esc(historyState.year)}-${esc(historyState.end)} · PH · ${metric==='sales'?ht('销售额榜','Sales ranking'):ht('销量榜','Units ranking')}</span></div><p class="trend-headline">${ht('所选范围内','Selected scope')}: <span class="up">${buckets.up.length} ${ht('项排名上升','rising')}</span> · <span class="down">${buckets.down.length} ${ht('项排名下降','falling')}</span></p>${list('up',ht('上升较明确','Clear upward direction'))}${list('down',ht('下降较明确','Clear downward direction'))}<div class="trend-statuses">${[['stable',ht('排名稳定','Stable')],['mixed',ht('波动、方向不明','Mixed direction')],['insufficient',ht('不足3个有效月，待观察','Under 3 ranked months')],['missing',ht('最近月份名次缺失，不判升降','Latest month missing')],['unknown',ht('名次均未公开','No published ranks')]].map(([status,label])=>`<span>${label} <b>${buckets[status].length}</b></span>`).join('')}</div>${otherDetails}<p class="history-method">${ht('按独立店铺／商品与类目判断；至少3个有效月且截至月有名次，结合月度走势、前后段平均与首末变化，方向一致才判升降。缺失月不填补，排名变化不等于销售增长。','Each shop / product and category is assessed separately. Direction requires at least 3 ranked months, a rank in the final month, and agreement between the time trend, early / late averages and endpoint change. Missing months are excluded. Rank changes do not imply sales growth.')}</p></article>`;
}
const historyMissingLabels={no_list:['无榜','No list','源站当月未提供该类目榜单','Source did not offer this category ranking that month'],absent:['—','—','本月导出未返回该实体；不据此判定掉榜','Entity absent from the monthly export; this does not establish a drop out of the ranking'],unranked:['待核实','Unverified','已返回该实体，网页名次尚待核实','Entity present; exact UI rank awaits verification'],not_imported:['待补','Pending','该月榜单尚未完成导入','Monthly ranking not imported'],conflict:['冲突','Conflict','该实体同月名次冲突，已排除趋势分析','Conflicting monthly ranks; excluded from analysis']};
function historyCell(p,a){
  if(p.rank==null){const labels=historyMissingLabels[p.status]||historyMissingLabels.absent;return `<td class="history-missing" title="${esc(ht(labels[2],labels[3]))}">${ht(labels[0],labels[1])}</td>`;}
  const cls=a.best!==a.worst?(p.rank===a.best?'up':p.rank===a.worst?'down':''):'';
  return `<td class="history-month ${cls}">${hr(p.rank)}</td>`;
}
function historyExtreme(a,best){
  const n=best?a.best:a.worst,ms=best?a.bestMonths:a.worstMonths;
  return `<td class="history-extreme ${a.best!==a.worst?(best?'up':'down'):''}">${n==null?'—':hr(n)}<div class="sub" title="${esc(ms.join(', '))}">${ms.map(hm).join(' · ')}</div></td>`;
}
function historyTable(groups,kind){
  if(!historyState.shops.size)return empty(ht('请先在品牌／店铺筛选中勾选至少一家店铺。','Choose at least one shop in the brand / shop filter.'));
  if(!groups.length)return empty(ht('所选店铺、类目和期间没有返回记录，请切换筛选。','No returned records for the selected shop, categories and period.'));
  const pageSize=40,pages=Math.ceil(groups.length/pageSize),page=Math.min(historyState.pages[kind],pages),slice=groups.slice((page-1)*pageSize,page*pageSize);
  return `<div class="history-table-hint">${ht('年度最高','Year best')} <span class="up">●</span> · ${ht('年度最低','Year worst')} <span class="down">●</span> · ${ht('相同最高／最低显示为中性色；横向滚动查看所有月份。','Equal best / worst ranks use a neutral color. Scroll horizontally for all months.')}</div><div class="tablewrap history-tablewrap" tabindex="0" role="region" aria-label="${ht(kind==='shop'?'店铺月度排名表':'商品月度排名表',kind==='shop'?'Monthly shop ranks':'Monthly product ranks')}"><table class="history-table"><thead><tr><th>${ht('类目','Category')}</th><th>${kind==='shop'?ht('品牌／店铺','Brand / Shop'):ht('单品／店铺','Product / Shop')}</th><th>${ht('年度最高','Year best')}</th><th>${ht('年度最低','Year worst')}</th>${historyMonths().map(m=>`<th>${hm(m)}</th>`).join('')}</tr></thead><tbody>${slice.map(g=>{const parts=g.category.split(' >> ');return `<tr><td><span class="badge">${esc(parts.at(-1))}</span> <span class="sub">${english?'L'+parts.length:parts.length+'级类目'}</span><div class="sub">${ht('上级','Parent')}：${esc(parts.slice(0,-1).join(' › ')||'—')}</div></td><td>${historyEntity(g)}</td>${historyExtreme(g.analysis,true)}${historyExtreme(g.analysis,false)}${g.points.map(p=>historyCell(p,g.analysis)).join('')}</tr>`}).join('')}</tbody></table></div>${pages>1?`<div class="history-pagination"><button data-history-page="${kind}" data-step="-1" ${page===1?'disabled':''}>${ht('上一页','Previous')}</button><span>${page} / ${pages} · ${groups.length} ${ht('条记录','records')}</span><button data-history-page="${kind}" data-step="1" ${page===pages?'disabled':''}>${ht('下一页','Next')}</button></div>`:''}`;
}
function historyView(){
  initHistory();const cats=historyCategories.filter(c=>historyState.categories.has(c)),scope={metric,months:historyMonths(),categories:cats,shops:historyState.shops,tasks:coverage.tasks};
  const sections=['shop','product'].map(kind=>{const groups=RankHistory.build(all,{...scope,kind});return `<section class="history-section" id="history-${kind}-section"><div class="history-section-title"><h2>${kind==='shop'?ht('竞品店铺月度排名','Competitor shop monthly ranks'):ht('竞品产品月度排名','Competitor product monthly ranks')} · ${esc(historyState.year)}</h2><span>${groups.length} ${kind==='shop'?ht('条店铺／类目记录','shop / category records'):ht('条产品／类目记录','product / category records')}</span></div>${groups.length?historyTrend(groups):''}${historyTable(groups,kind)}</section>`}).join('');
  return `<div class="history-panel"><h2>${ht('竞品排名变化','Ranking Changes')} · ${esc(historyState.year)}</h2>${historyFilters()}<p class="history-scope">${ht('统计窗口','Period')}：${esc(historyState.year)}-01 — ${esc(historyState.year)}-${esc(historyState.end)} · ${ht('完整自然月','Full calendar months')} · ${ht('店铺按稳定链接独立统计，商品按商品 ID 与类目分别统计。年度最高／最低仅使用已公开的有效名次。','Shops use stable URL identities; products use item ID and category. Annual extremes include only published ranks.')}</p><p class="history-scope">${ht('缺失说明：无榜＝源站当月未提供；—＝当月未返回该实体；待核实＝实体存在但网页名次尚待核实；待补＝榜单未导入。','Missing values: No list = not offered by source; — = entity not returned; Unverified = exact UI rank awaits verification; Pending = ranking not imported.')}</p>${sections}</div>`;
}
function bindHistory(){
  const reset=()=>{const listTop=$('history-shop-list')?.scrollTop||0;historyState.pages={shop:1,product:1};render();if($('history-shop-list'))$('history-shop-list').scrollTop=listTop;sizeHistoryShopMenu();};
  $('history-year').onchange=e=>{historyState.year=e.target.value;historyState.end=months.filter(m=>m.startsWith(historyState.year)).sort().at(-1)?.slice(5)||'12';reset();};
  $('history-end').onchange=e=>{historyState.end=e.target.value;reset();};
  $('history-shop-picker').ontoggle=e=>{historyState.shopOpen=e.target.open;if(e.target.open){if($('history-category'))$('history-category').open=false;historyState.categoryOpen=false;sizeHistoryShopMenu();}};
  $('history-shop-picker').onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();closeHistoryShopMenu(true);}};
  $('history-shop-search').oninput=e=>{historyState.query=e.target.value;$('history-shop-list').innerHTML=historyShopOptions();};
  $('history-shop-list').onchange=e=>{
    const box=e.target.closest('[data-history-shop]');if(!box)return;
    const key=box.dataset.historyShop;historyState.shopOpen=true;
    box.checked?historyState.shops.add(key):historyState.shops.delete(key);reset();
    [...document.querySelectorAll('[data-history-shop]')].find(b=>b.dataset.historyShop===key)?.focus({preventScroll:true});
  };
  document.querySelectorAll('[data-history-shops]').forEach(button=>button.onclick=()=>{
    const mode=button.dataset.historyShops;if(mode==='done'){closeHistoryShopMenu(true);return;}
    historyState.shopOpen=true;
    historyState.shops=new Set(mode==='all'?[...historyShops.keys()]:mode==='default'&&historyDefaultShop?[historyDefaultShop]:[]);
    if(mode==='default')historyState.query='';reset();
    document.querySelector('[data-history-shops="'+mode+'"]').focus({preventScroll:true});
  });
  CategoryPicker.bind('history-category',{tree:categoryTree,multiple:true,defaults:()=>historyState.defaultCategories,onOpen:open=>{historyState.categoryOpen=open;if(open)closeHistoryShopMenu();},onChange:value=>{historyState.categories=value;reset();}});
  document.querySelectorAll('[data-history-page]').forEach(button=>button.onclick=()=>{const kind=button.dataset.historyPage;historyState.pages[kind]+=Number(button.dataset.step);render();$('history-'+kind+'-section').scrollIntoView({block:'start'});});
}

document.addEventListener('click',e=>{if(historyState?.shopOpen&&!e.target.closest('#history-shop-picker'))closeHistoryShopMenu();});
window.addEventListener('resize',sizeHistoryShopMenu);
