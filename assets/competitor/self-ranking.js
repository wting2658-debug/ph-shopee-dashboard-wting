(function(root,factory){
  const api=factory(typeof module==='object'&&module.exports?require('./rank-history.js'):root.RankHistory);
  if(typeof module==='object'&&module.exports)module.exports=api;else root.SelfRanking=api;
})(typeof window==='undefined'?globalThis:window,function(H){
  'use strict';
  const defaults=['Beauty','Beauty >> Skincare','Beauty >> Makeup'];
  const key=g=>JSON.stringify([g.id,g.category]);
  function yearMonths(rows,tasks,year){
    const dates=[...rows,...tasks].map(r=>r.month).filter(m=>/^\d{4}-\d{2}$/.test(m)&&m.slice(0,4)===String(year)).sort();
    const end=Number(dates.at(-1)?.slice(5)||0);
    return Array.from({length:end},(_,i)=>year+'-'+String(i+1).padStart(2,'0'));
  }
  function build(rows,{year,metric,shop,categories,tasks=[]}){
    const own=rows.filter(r=>r.skintific&&(!shop||H.shopKey(r)===shop));
    const months=yearMonths(rows,tasks,year),scope={metric,months,categories,tasks};
    return {months,shops:H.build(own,{...scope,kind:'shop'}),products:H.build(own,{...scope,kind:'product'})};
  }
  // Category level first, then the exact rank in the selected month. Missing ranks sort last.
  function sort(groups,month){
    const at=g=>g.points.find(p=>p.month===month)?.rank??Infinity;
    return [...groups].sort((a,b)=>a.category.split(' >> ').length-b.category.split(' >> ').length||at(a)-at(b)||a.category.localeCompare(b.category)||a.id.localeCompare(b.id));
  }
  function defaultProducts(groups,month,limit=3){
    const latest=g=>g.analysis.last?.month||'';
    return [...groups].sort((a,b)=>(a.points.find(p=>p.month===month)?.rank??Infinity)-(b.points.find(p=>p.month===month)?.rank??Infinity)||latest(b).localeCompare(latest(a))||(a.analysis.last?.rank??Infinity)-(b.analysis.last?.rank??Infinity)||a.id.localeCompare(b.id)).slice(0,limit).map(key);
  }
  // Separate segments prevent a line implying a rank across a missing or unpublished month.
  function segments(points){
    const out=[];let current=[];
    for(let i=0;i<points.length;i++){
      if(H.validRank(points[i].rank))current.push({...points[i],index:i});
      else if(current.length){out.push(current);current=[];}
    }
    if(current.length)out.push(current);return out;
  }
  function overlaps(groups){
    const signatures=new Map();
    for(const g of groups){if(!g.analysis.count)continue;const s=JSON.stringify(g.points.map(p=>p.rank));signatures.set(s,(signatures.get(s)||0)+1);}
    return [...signatures.values()].filter(n=>n>1).length;
  }
  function comparisonRank(rows,g,{month,metric,shop}){
    const records=rows.filter(r=>r.skintific&&r.kind===g.kind&&r.metric===metric&&r.month===month&&r.category===g.category&&H.entityKey(r)===g.id&&(!shop||H.shopKey(r)===shop));
    const values=[...new Set(records.map(r=>H.validRank(r.rank)?r.rank:null))];
    return values.length===1?values[0]:null;
  }
  return {defaults,key,yearMonths,build,sort,defaultProducts,segments,overlaps,comparisonRank};
});
