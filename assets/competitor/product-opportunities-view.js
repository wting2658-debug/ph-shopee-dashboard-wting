'use strict';
const opportunityPalette=['#3d67e8','#22a191','#ee6b68','#d99720','#7b67d9','#39a8c8','#df7db1','#80a34b','#ed9561','#647fba','#a47fc7','#54b5a0'];
function opportunityColor(name,scope){return opportunityPalette[[...scope.groups].sort((a,b)=>b.observed-a.observed||a.name.localeCompare(b.name)).findIndex(g=>g.name===name)%opportunityPalette.length];}
function opportunityType(name){return `<span class="badge">${esc(name)}</span>`;}
function opportunityCount(value,observed=0){return value==null?`<span class="types-missing">${observed?'≥'+observed:'—'}</span>`:String(value);}
function opportunityPeak(g,ratio=false){
  const a=g.analysis;if(a.peak==null)return '<span class="flat">—</span>';
  return `<strong class="types-peak-value">${a.peak}${ratio?'<span>/20</span>':ht(' 款',' products')}</strong><span class="sub" title="${esc(a.peakMonths.map(hm).join(' / '))}">${hm(a.peakMonths[0])}</span>`;
}
function opportunityRiseText(g){
  const a=g.analysis;
  return ht(`${g.name} 从${hm(a.first.month)} ${a.first.count}款增至${hm(a.last.month)} ${a.last.count}款`,`${g.name}: ${a.first.count} products in ${hm(a.first.month)} to ${a.last.count} in ${hm(a.last.month)}`);
}
function opportunityCommonText(g){const a=g.analysis;return ht(`${g.name} 月均${a.average.toFixed(1)}款，年度峰值${a.peak}款（${hm(a.peakMonths[0])}）`,`${g.name}: ${a.average.toFixed(1)} products per month; peak ${a.peak} (${hm(a.peakMonths[0])})`);}
function opportunityConclusion(scope,opportunity=false){
  const leaders=opportunity?scope.opportunities:scope.rising,common=scope.common.filter(g=>!scope.rising.includes(g));
  let headline,detail;
  if(leaders.length){
    headline=opportunity?ht('年度机会重点关注：','Annual opportunities to watch: '):ht('上升最明确：','Clearest increases: ');
    headline+=leaders.slice(0,3).map(g=>esc(g.name)).join('、');
    detail=leaders.slice(0,3).map(g=>g.analysis.status==='up'?opportunityRiseText(g):opportunityCommonText(g)).join(ht('；','; '))+ht('。','.');
  }else if(!opportunity&&common.length){
    headline=ht('年度持续入榜：','Types consistently present: ')+common.slice(0,3).map(g=>esc(g.name)).join('、');
    detail=common.slice(0,2).map(opportunityCommonText).join(ht('；','; '))+ht('。暂未观察到方向明确的席位增长。','. No clear increase in Top 20 places has been confirmed.');
  }else{
    headline=ht('暂无可确认的年度增长机会','No confirmed annual growth opportunity');
    detail=ht(`当前有${scope.completeMonths}个可完整统计的月份，现有数据不足以确认持续增长；可结合下方单品继续观察。`,`${scope.completeMonths} months have complete rankings. The available data does not establish sustained growth; review individual products below.`);
  }
  const decline=scope.declining.slice(0,3).map(g=>g.name).join('、');
  return `<div class="types-conclusion"><strong>${scope.year}${opportunity?ht(' 年机会结论',' opportunities'):ht(' 年趋势结论',' annual trend')}</strong><div><h3>${headline}</h3><p>${esc(detail)}</p>${decline?`<p>${ht('回落关注：','Declining presence: ')}${esc(decline)}。</p>`:''}</div></div>`;
}
function opportunityDonut(scope){
  const groups=scope.groups.filter(g=>g.observed>0).sort((a,b)=>b.observed-a.observed||a.name.localeCompare(b.name)),total=scope.current.total;
  if(!total)return empty(ht('当前月份没有可确认名次的 Top20 商品。','No products with confirmed Top 20 ranks in this month.'));
  const cx=260,cy=182,r=105,circ=2*Math.PI*r,labels=[];let offset=0;
  const segments=groups.map(g=>{
    const length=g.observed/total*circ,angle=(offset+length/2)/circ*Math.PI*2-Math.PI/2,x=cx+Math.cos(angle)*128,y=cy+Math.sin(angle)*128;
    labels.push({g,x,y,right:x>=cx});
    const result=`<circle class="types-donut-segment" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${opportunityColor(g.name,scope)}" stroke-width="40" stroke-dasharray="${Math.max(0,length-(groups.length>1?1.5:0))} ${circ}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})" tabindex="0"><title>${esc(g.name)}: ${g.observed}${ht('款',' products')}</title></circle>`;offset+=length;return result;
  }).join('');
  for(const right of [false,true]){const side=labels.filter(l=>l.right===right).sort((a,b)=>a.y-b.y);let last=22;for(const l of side){l.labelY=Math.max(l.y,last+34);last=l.labelY;}if(side.at(-1)?.labelY>325){const excess=side.at(-1).labelY-325;side.forEach(l=>l.labelY-=excess);}}
  const labelMarkup=labels.map(l=>`<g class="types-chart-label"><path d="M${l.x},${l.y} L${l.right?397:123},${l.labelY} L${l.right?410:111},${l.labelY}" fill="none" stroke="${opportunityColor(l.g.name,scope)}"/><text x="${l.right?416:105}" y="${l.labelY-4}" text-anchor="${l.right?'start':'end'}"><tspan x="${l.right?416:105}">${esc(l.g.name)}</tspan><tspan x="${l.right?416:105}" dy="19">${l.g.observed}${ht(' 个',' products')}</tspan></text></g>`).join('');
  return `<svg class="types-donut" viewBox="0 0 550 370" role="img" aria-label="${esc(groups.map(g=>g.name+': '+g.observed).join('; '))}"><title>${ht('Top20 产品类型结构','Top 20 product type distribution')}</title>${segments}${labelMarkup}</svg><div class="types-legend">${groups.map(g=>`<span><i style="background:${opportunityColor(g.name,scope)}"></i>${esc(g.name)}</span>`).join('')}</div><p class="types-chart-note">${ht(`当前已确认 ${total} 款 Top20 商品；${scope.current.complete?'类型款数之和为 '+total+'。':'榜单不完整，仅展示已确认名次的商品。'}`,`${total} confirmed Top 20 products. ${scope.current.complete?'Type counts total '+total+'.':'The ranking is incomplete; only confirmed products are shown.'}`)}</p>`;
}
function opportunityMatrix(scope){
  if(!scope.groups.length)return empty(ht('该年度和类目暂无可统计的产品榜。','No product rankings for this year and category.'));
  return `<div class="tablewrap types-matrixwrap" tabindex="0" role="region" aria-label="${ht('年度产品类型趋势表','Annual product type trends')}"><table class="types-matrix" style="min-width:${245+scope.months.length*(english?80:61)}px"><colgroup><col class="types-name-col"><col class="types-peak-col">${scope.months.map(()=>'<col>').join('')}</colgroup><thead><tr><th>${ht('产品类型','Product type')}</th><th>${ht('年度峰值','Annual peak')}</th>${scope.months.map(m=>`<th class="${m===scope.month?'types-active-month':''}">${hm(m)}</th>`).join('')}</tr></thead><tbody>${scope.groups.map(g=>`<tr><td>${opportunityType(g.name)}</td><td>${opportunityPeak(g)}</td>${g.points.map(p=>`<td class="${p.month===scope.month?'types-active-month ':''}${p.count>0&&p.count===g.analysis.peak?'types-peak-cell ':''}${p.count===0?'types-zero':''}" title="${p.status==='no_list'?ht('源站当月未提供榜单','No ranking offered by source'):p.status==='not_imported'?ht('榜单待导入','Ranking not imported'):p.status==='partial'?ht('榜单不完整；显示已确认商品的下限，不参与年度趋势判断','Incomplete ranking; observed lower bound, excluded from trend analysis'):''}">${opportunityCount(p.count,p.observed)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function opportunityProduct(r){
  return `<article class="types-product">${image(r)}<div><div class="types-product-title" title="${esc(r.product_name)}">${link(r.product_url,r.product_name)}</div><div class="types-product-meta"><strong>${hr(r.rank)}</strong>${r.isNew===true?`<b class="types-new">${ht('新入榜','New in Top 20')}</b>`:''}${link(r.shop_url,r.shop_name)}</div><div class="types-product-id">${ht('商品 ID','Item ID')} ${esc(r.id)}${r.oldRank!=null?ht(` · 对比月第${r.oldRank}名`,` · Previous #${r.oldRank}`):''}</div></div></article>`;
}
function opportunityProducts(g){
  if(!g.items.length)return '<span class="flat">—</span>';
  return `<div class="types-product-grid">${g.items.slice(0,4).map(opportunityProduct).join('')}</div>${g.items.length>4?`<details class="types-more-products"><summary>${ht(`展开其余 ${g.items.length-4} 款商品明细`,`Show ${g.items.length-4} more products`)}</summary><div class="types-product-grid">${g.items.slice(4).map(opportunityProduct).join('')}</div></details>`:''}`;
}
function opportunityShops(g){return g.shops.length?`<ul class="types-shops">${g.shops.map(s=>`<li>${link(s.url,s.name)}${s.id?`<small>ID ${esc(s.id)}</small>`:''}</li>`).join('')}</ul>`:'<span class="flat">—</span>';}
function opportunityDetails(scope){
  if(!scope.groups.length)return empty(ht('暂无类型明细，请切换类目或月份。','No type details; try another category or month.'));
  return `<div class="tablewrap types-detailwrap" tabindex="0" role="region" aria-label="${ht('机会产品类型与商品明细','Product type opportunities and product details')}"><table class="types-detail-table"><colgroup><col class="types-detail-name"><col class="types-detail-count"><col class="types-detail-count"><col class="types-detail-delta"><col class="types-detail-peak"><col><col class="types-detail-shop"></colgroup><thead><tr><th>${ht('产品类型','Product type')}</th><th>${hm(scope.month)} Top20</th><th>${scope.compareValid?hm(scope.compareMonth):ht('对比月','Compare')} Top20</th><th>${scope.compareValid?ht('较'+hm(scope.compareMonth),'vs '+hm(scope.compareMonth)):ht('较对比月','Change')}</th><th>${ht('年度峰值','Annual peak')}</th><th>${ht('本月新增 / 代表单品','New / representative products this month')}</th><th>${ht('代表店铺','Representative shops')}</th></tr></thead><tbody>${scope.groups.map(g=>`<tr><td>${opportunityType(g.name)}</td><td><strong class="types-current-count">${opportunityCount(g.current,g.observed)}</strong>${g.current!=null?'<small class="types-denominator">/20</small>':''}</td><td><strong>${opportunityCount(g.previous,scope.previous?.top.filter(r=>r.type===g.name).length||0)}</strong>${g.previous!=null?'<small class="types-denominator">/20</small>':''}</td><td>${risingMovement(g.delta)}</td><td>${opportunityPeak(g,true)}</td><td>${opportunityProducts(g)}</td><td>${opportunityShops(g)}</td></tr>`).join('')}</tbody></table></div>`;
}
function productOpportunitiesView(){
  const scope=ProductOpportunities.build(all,{month:$('month').value,compareMonth:$('compare').value,category:cat(),metric,tasks:coverage.tasks});
  const period=scope.months.length?`${hm(scope.months[0])}—${hm(scope.months.at(-1))}`:'';
  return `<div class="types-view${english?' types-english':''}"><div class="types-overview"><section class="types-panel types-structure"><h2>${ht('Top20 产品类型结构','Top 20 product type distribution')}</h2><p class="types-subtitle">${ht('按当前国家、类目、月份拆分','For the selected country, category and month')}</p>${opportunityDonut(scope)}</section><section class="types-panel types-trends"><h2>${ht('潜力趋势品类','Potential type trends')}</h2><p class="types-subtitle">${ht(`展示 ${scope.year} 年（${period}）各产品类型进入 Top20 的月度数量与年度趋势`,`Monthly Top 20 product counts and trends for ${scope.year} (${period})`)}</p>${opportunityConclusion(scope)}${opportunityMatrix(scope)}<p class="types-method">${ht('数量为商品款数；绿色数字表示年度峰值，浅绿列为所选月份。— 表示无榜或数据不可确认，≥ 表示不完整榜单中的已确认下限，均不填作 0。','Counts represent products. Green values mark annual peaks; the pale green column is the selected month. — indicates unavailable data; ≥ is an observed lower bound from an incomplete ranking. Neither is treated as zero.')}</p></section></div><section class="types-panel types-opportunities"><h2>${ht('机会产品类型','Product type opportunities')}</h2><p class="types-subtitle">${ht(`表格按所选月份对比；上方结论基于 ${scope.year} 年全部已导入月份（${period}）`,`The table compares the selected months; annual findings use all imported months in ${scope.year} (${period})`)}</p>${opportunityConclusion(scope,true)}${scope.compareMonth&&!scope.compareValid?`<p class="types-method">${ht('对比月份须早于当前月份，当前未计算月度变化。','Comparison month must precede the selected month; monthly changes are not calculated.')}</p>`:''}${opportunityDetails(scope)}<p class="types-method">${ht('口径：同国家、同类目、同榜单，不叠加父子类目榜单，按商品 ID 去重。类型优先使用所选四级类目，其次三级类目，否则按名称归类；Other 需进一步识别，不直接视为单一新品机会。新入榜指相对对比月新进入 Top20，不代表首次上架。年度趋势至少使用 3 个完整月份，结合首末款数、整体走势及前后段平均；款数占比和席位增长不代表销售额份额或市场规模增长。','Method: one country, category and metric; category rankings are not added together and items are deduplicated by ID. Types use the selected L4 category first, then L3, otherwise product names. Other needs further classification and is not a single product opportunity. New in Top 20 refers to the comparison month, not launch dates. Annual direction requires at least three complete months and agreement between endpoints, overall trend and early/late averages. Product counts and ranking presence do not measure sales share or market growth.')}</p></section></div>`;
}
