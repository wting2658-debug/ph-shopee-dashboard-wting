(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./rank-history.js'));
  else root.RisingCompetitors=factory(root.RankHistory);
})(typeof window==='undefined'?globalThis:window,function(H){
  'use strict';
  function build(rows,{kind,metric,month,compareMonth='',category,tasks=[]}){
    const year=month.slice(0,4),months=Array.from({length:Number(month.slice(5))},(_,i)=>year+'-'+String(i+1).padStart(2,'0'));
    const compareValid=!!compareMonth&&compareMonth<month;
    const previous=new Map((compareValid?H.build(rows,{kind,metric,months:[compareMonth],categories:[category],tasks}):[]).map(g=>[g.id,g.points[0]]));
    const groups=H.build(rows,{kind,metric,months,categories:[category],tasks});
    const current=groups.filter(g=>g.points.at(-1).status!=='absent'&&g.points.at(-1).status!=='no_list'&&g.points.at(-1).status!=='not_imported'&&!g.sample.skintific);
    const candidates=current.filter(g=>H.validRank(g.points.at(-1).rank)&&g.points.at(-1).rank<=20).map(g=>{
      const rank=g.points.at(-1).rank,comparison=previous.get(g.id),a=g.analysis;
      const compareRank=H.validRank(comparison?.rank)?comparison.rank:null;
      const monthDelta=compareRank==null?null:compareRank-rank;
      const firstDelta=a.first.rank-rank;
      return {...g,rank,compareRank,monthDelta,firstDelta,score:(monthDelta??0)+firstDelta,isRising:monthDelta>0||firstDelta>0};
    }).sort((a,b)=>b.score-a.score||(b.firstDelta-a.firstDelta)||a.rank-b.rank||a.id.localeCompare(b.id));
    return {year,month,compareMonth,compareValid,rows:candidates,leaders:candidates.filter(g=>g.isRising),unknownCurrent:current.filter(g=>!H.validRank(g.points.at(-1).rank)).length};
  }
  return {build};
});
