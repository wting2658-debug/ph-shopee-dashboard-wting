'use strict';
function risingName(g,short=false){
  const r=g.sample,name=(g.kind==='product'?r.product_name:r.shop_name||r.brand)||g.id;
  const limit=g.kind==='product'?112:70,display=short&&Array.from(name).length>limit?Array.from(name).slice(0,limit).join('')+'…':name;
  return `<span title="${esc(name)}">${link(g.kind==='product'?r.product_url:r.shop_url,display)}</span>`;
}
function risingMovement(delta){
  return delta==null?'<span class="flat">—</span>':delta===0?`<span class="flat">${ht('持平','Unchanged')}</span>`:`<span class="${delta>0?'up':'down'}">${delta>0?'↑':'↓'}${Math.abs(delta)}</span>`;
}
function risingTrend(g,scope){
  const a=g.analysis,now=hm(scope.month),first=hm(a.first.month);
  if(a.count===1)return ht(`${now}${hr(g.rank)}；年内首次取得有效排名，待观察`,`${now} ${hr(g.rank)}; first published rank this year; watch for more observations`);
  const best=ht(`年内最佳${hr(a.best)}`,`year best ${hr(a.best)}`);
  if(g.firstDelta>0){
    const lead=g.rank===a.best?ht(`${now}升至年内最佳${hr(g.rank)}`,`${now} reached the year best ${hr(g.rank)}`):ht(`${now}${hr(g.rank)}`,`${now} ${hr(g.rank)}`);
    return `${lead}${ht(`，较${first}提升${g.firstDelta}位`,`, up ${risingPlaces(g.firstDelta)} from ${first}`)}${g.rank===a.best?'':ht('；','; ')+best}`;
  }
  if(g.monthDelta>0)return ht(`${now}${hr(g.rank)}，较${hm(scope.compareMonth)}提升${g.monthDelta}位；${best}`,`${now} ${hr(g.rank)}, up ${risingPlaces(g.monthDelta)} from ${hm(scope.compareMonth)}; ${best}`);
  const bestMonth=hm(a.bestMonths[0]);
  return ht(`${now}${hr(g.rank)}；${bestMonth}最佳${hr(a.best)}`,`${now} ${hr(g.rank)}; best ${hr(a.best)} in ${bestMonth}`);
}
function risingPlaces(n){return `${n} ${n===1?'place':'places'}`;}
function risingHeroDetail(g,scope){
  const a=g.analysis;
  const change=g.firstDelta>0?ht(`提升${g.firstDelta}位`,`up ${risingPlaces(g.firstDelta)}`):g.firstDelta<0?ht(`下降${-g.firstDelta}位`,`down ${risingPlaces(-g.firstDelta)}`):ht('持平','unchanged');
  const baseline=a.count===1?ht('年内首次取得有效排名','first published rank this year'):ht(`较${hm(a.first.month)}${change}`,`${change} since the first published rank in ${hm(a.first.month)}`);
  return ht(`${hm(scope.month)}${hr(g.rank)}，${baseline}；年内最佳${hr(a.best)}；${scope.year}年累计入榜${a.count}个月。`,`${hm(scope.month)} ${hr(g.rank)}, ${baseline}; year best ${hr(a.best)}; ${a.count} ranked months in ${scope.year}.`);
}
function risingFollow(g,scope){
  const delta=g.firstDelta>0?ht(`较首次入榜上升${g.firstDelta}位`,`up ${risingPlaces(g.firstDelta)} from first rank`):g.monthDelta>0?ht(`较${hm(scope.compareMonth)}上升${g.monthDelta}位`,`up ${risingPlaces(g.monthDelta)} from ${hm(scope.compareMonth)}`):ht('继续观察','watch');
  return `${risingName(g,true)} <span class="rising-follow-detail">（${hr(g.rank)} · ${delta}）</span>`;
}
function risingConclusion(scope,kind){
  const leader=scope.leaders[0],product=kind==='product';
  const label=product?ht('竞品产品关键结论','Key product findings'):ht('竞品店铺关键结论','Key shop findings');
  let body='';
  if(leader){
    body=`<h3>${leader.score>0?ht('综合上升最明显：','Strongest combined rise: '):ht('本期回升值得关注：','Current rebound to watch: ')}${risingName(leader,true)}</h3><p>${risingHeroDetail(leader,scope)}</p>${product?`<p>${ht('类型','Type')}：${esc(type(leader.sample))} · ${ht('店铺','Shop')}：${link(leader.sample.shop_url,leader.sample.shop_name)}</p>`:''}${scope.leaders.length>1?`<p class="rising-follow">${ht('同时关注：','Also watch: ')}${scope.leaders.slice(1,4).map(g=>risingFollow(g,scope)).join('； ')}</p>`:''}`;
    if(leader.score<=0&&leader.firstDelta<0)body+=`<p>${ht('该竞品较年内首次有效排名仍下降','Still below its first published rank this year by ')} ${Math.abs(leader.firstDelta)} ${ht('位，本期回升尚未抵消此前回落。','places; the recent rebound has not offset the earlier decline.')}</p>`;
  }else body=`<h3>${ht('暂未发现可确认的上升竞品','No confirmed rising competitors in this selection')}</h3><p>${ht('当前有','There are ')} ${scope.rows.length} ${ht('个已公开名次的 Top 20 竞品；现有可比名次未显示提升，缺少对比数据的竞品仍需观察。','competitors with published Top 20 ranks. Available rank comparisons show no improvement; competitors without comparison data require further observation.')}</p>`;
  return `<div class="rising-conclusion"><strong class="rising-key-label">${label}</strong><div>${body}</div></div>`;
}
function risingCompetitorTable(scope,kind){
  const product=kind==='product';
  if(!scope.rows.length)return empty(ht('当前导出没有符合条件的 Top 20 竞品记录，请切换类目、月份或榜单口径。','No qualifying Top 20 competitors in this export. Try another category, month or metric.'));
  const compareHeader=scope.compareValid?ht(`较${hm(scope.compareMonth)}排名变化`,`vs ${hm(scope.compareMonth)} rank change`):ht('对比月排名变化','Comparison rank change');
  const cols=product?'<col class="rising-rank-col"><col><col class="rising-type-col"><col class="rising-shop-col"><col class="rising-change-col"><col class="rising-first-col"><col class="rising-trend-col">':'<col class="rising-rank-col"><col><col class="rising-change-col"><col class="rising-first-col"><col class="rising-trend-col">';
  return `<div class="tablewrap rising-tablewrap" tabindex="0" role="region" aria-label="${product?ht('上升竞品商品表','Rising competitor products'):ht('上升竞品店铺表','Rising competitor shops')}"><table class="rising-table ${product?'rising-products':'rising-shops'}"><colgroup>${cols}</colgroup><thead><tr><th>${ht(hm(scope.month)+'排名',hm(scope.month)+' rank')}</th><th>${product?ht('单品','Product'):ht('店铺／品牌','Shop / Brand')}</th>${product?`<th>${ht('类型','Type')}</th><th>${ht('店铺','Shop')}</th>`:''}<th>${compareHeader}</th><th>${ht('较首次入榜','vs first rank')}</th><th>${ht('趋势摘要','Trend summary')}</th></tr></thead><tbody>${scope.rows.map(g=>`<tr class="${g.rank<=3?'top':''}"><td><span class="rank">${hr(g.rank)}</span></td><td><div class="entity">${image(g.sample)}<div class="rising-entity-name">${risingName(g)}${g.sample.account_owned?`<div class="sub">${ht('同账号其他品牌','Other account brand')}</div>`:''}</div></div></td>${product?`<td><span class="badge">${esc(type(g.sample))}</span></td><td class="rising-shop-name">${link(g.sample.shop_url,g.sample.shop_name)}</td>`:''}<td class="rising-delta" title="${g.compareRank==null?ht('对比月未提供有效名次','No valid comparison rank'):`${esc(scope.compareMonth)}: ${g.compareRank} → ${g.rank}`}">${risingMovement(g.monthDelta)}</td><td class="rising-delta" title="${g.analysis.first.month}: ${g.analysis.first.rank} → ${g.rank}">${risingMovement(g.firstDelta)}</td><td class="rising-trend">${risingTrend(g,scope)}</td></tr>`).join('')}</tbody></table></div>`;
}
function risingCompetitorsView(){
  const month=$('month').value,compareMonth=$('compare').value;
  return `<div class="rising-view">${['shop','product'].map(kind=>{
    const product=kind==='product',scope=RisingCompetitors.build(all,{kind,metric,month,compareMonth,category:cat(),tasks:coverage.tasks});
    const title=product?ht('上升竞品产品','Rising competitor products'):ht('上升竞品店铺','Rising competitor shops');
    const subtitle=ht(`当前月 Top20 内，结合对比月变化和 ${scope.year} 年入榜轨迹筛选出的竞品${product?'单品':'店铺'}`,`Competitor ${product?'products':'shops'} in the current Top 20, assessed using comparison-month changes and the ${scope.year} ranking history.`);
    const comparisonNote=compareMonth&&!scope.compareValid?ht('对比月份须早于当前月份；当前仅使用年内首次有效排名比较。','The comparison month must precede the selected month. Only the first valid rank this year is used here.'):!compareMonth?ht('未选择对比月；当前使用年内首次有效排名比较。','No comparison month selected; the first valid rank this year is used.'):'';
    return `<section class="rising-panel" id="rising-${kind}-section"><h2>${title}</h2><p class="rising-subtitle">${subtitle}</p>${comparisonNote?`<p class="rising-comparison-note">${comparisonNote}</p>`:''}${risingConclusion(scope,kind)}${risingCompetitorTable(scope,kind)}<p class="rising-method">${ht('统计说明：综合排序＝对比月名次提升＋较年内首次有效入榜名次提升，下降记负值，缺失项不计；保留当前 Top20 中的持平及回落竞品供对照。首次入榜和月数仅计算有公开名次的月份，不代表首次上架；排名变化不等于销售增长。','Method: combined order uses the comparison-month rank gain plus the gain since the first published rank this year; declines count negatively and missing comparisons do not contribute. Stable and declining current Top 20 competitors remain for context. First rank and month counts use published ranks only, not product launch dates. Rank changes do not imply sales growth.')} ${scope.unknownCurrent?ht(`当前另有 ${scope.unknownCurrent} 个竞品未公开具体名次，未纳入 Top20 判断。`,`${scope.unknownCurrent} additional competitors have no published current rank and cannot be classified as Top 20.`):''}${product?' '+ht('产品类型优先使用三级类目，否则按商品名称归类。','Product types use the source L3 category when present, otherwise they are inferred from names.'):''}</p></section>`;
  }).join('')}</div>`;
}
