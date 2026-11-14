(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./rank-history.js'));
  else root.ProductOpportunities=factory(root.RankHistory);
})(typeof window==='undefined'?globalThis:window,function(H){
  'use strict';
  const categoryTypes={'Face Mask & Packs':'Face Mask','Facial Serum & Essence':'Serum/Essence','Facial Moisturizer':'Moisturizer','Facial Cleanser':'Cleanser','Face Sunscreen':'Sunscreen','Sun Care':'Sunscreen','Facial Mist':'Facial Mist','Facial Oil':'Facial Oil','Toner':'Toner','Lip Treatment':'Lip Care','Eye Treatment':'Eye Care','Acne Treatment':'Acne Treatment','After Sun Face Care':'After Sun Care','Face Scrub & Peel':'Scrub/Peel','Body Cream, Lotion & Butter':'Body Lotion','Body Deodorants':'Deodorant','Lips':'Lip Makeup','Makeup Removers':'Makeup Remover','Hair Tools':'Hair Tools','Makeup Accessories':'Makeup Accessories'};
  function classify(row){
    const path=String(row.category||'').split(' >> '),leaf=path[2],n=String(row.product_name||'').toLowerCase();
    if(path[3]&&path[3]!=='Others')return {name:path[3],basis:'category'};
    if(categoryTypes[leaf])return {name:categoryTypes[leaf],basis:'category'};
    if(/\b(ipl|hair removal|beauty device|booster pro|booster-pro|age-r|microcurrent)\b/.test(n))return {name:'Beauty Device',basis:'name'};
    if(/\b(skincare set|skin care set|skincare kit|routine set|cleanse.{0,8}treat set|\d+\s*pc.{0,20}set)\b/.test(n))return {name:'Skincare Set',basis:'name'};
    if(/\b(lipstick|lip tint|lip gloss|lipgloss|lip stain|lip cream|teddy tint)\b/.test(n))return {name:'Lip Makeup',basis:'name'};
    if(/\bconcealer\b/.test(n))return {name:'Concealer',basis:'name'};
    if(/\bcushion\b/.test(n))return {name:'Cushion',basis:'name'};
    if(/\bfoundation\b/.test(n))return {name:'Foundation',basis:'name'};
    if(/\b(blush|blusher|contour|face powder|setting powder|pressed powder)\b/.test(n))return {name:'Face Makeup',basis:'name'};
    if(/\b(mascara|eyeliner|eye shadow|eyeshadow|eyebrow)\b/.test(n))return {name:'Eye Makeup',basis:'name'};
    if(/\b(soap|body bar|shower gel|body wash)\b/.test(n))return {name:'Body Soap/Wash',basis:'name'};
    if(/\b(sunscreen|sunblock|sun serum|sunexpert)\b/.test(n))return {name:'Sunscreen',basis:'name'};
    if(/\b(body lotion|body cream|body butter|whitening lotion|milk.{0,15}lotion)\b/.test(n))return {name:'Body Lotion',basis:'name'};
    if(/\b(deodorant|antiperspirant)\b/.test(n))return {name:'Deodorant',basis:'name'};
    if(/\b(micellar|makeup remover|cleansing balm|cleansing oil)\b/.test(n))return {name:'Makeup Remover',basis:'name'};
    if(/\b(toner|toning|toner pad)\b/.test(n))return {name:'Toner',basis:'name'};
    if(/\b(cleanser|facial wash|cleansing foam)\b/.test(n))return {name:'Cleanser',basis:'name'};
    if(/\b(eye cream|eye serum)\b/.test(n))return {name:'Eye Care',basis:'name'};
    if(/\b(lip balm|lip treatment|lip mask)\b/.test(n))return {name:'Lip Care',basis:'name'};
    if(/\b(cream|moisturizer|moisturiser)\b/.test(n))return {name:'Moisturizer',basis:'name'};
    if(/\b(mask|sheet mask)\b/.test(n))return {name:'Face Mask',basis:'name'};
    if(/\b(mist|spray)\b/.test(n))return {name:'Facial Mist',basis:'name'};
    if(/\b(serum|ampoule|essence)\b/.test(n))return {name:'Serum/Essence',basis:'name'};
    if(/\b(hair dryer|hairdryer|hair straightener|hair curler|airwrap|hairstyler|multistyler)\b/.test(n))return {name:'Hair Tools',basis:'name'};
    if(path[1]==='Beauty Sets & Packages')return {name:'Beauty Set',basis:'category'};
    if(leaf==='Face')return {name:'Face Makeup',basis:'category'};
    return {name:'Other',basis:'name'};
  }
  function monthly(rows,task){
    if(task?.status==='source_not_listed')return {status:'no_list',complete:false,top:[],records:new Map(),total:0,unknown:0};
    if(!rows.length)return {status:task?.status==='complete'?'complete':'not_imported',complete:task?.status==='complete',top:[],records:new Map(),total:0,unknown:0};
    const records=new Map(),conflicts=new Set();let missingIds=0;
    for(const r of rows){const id=H.entityKey(r);if(!id){missingIds++;continue;}if(records.has(id)&&records.get(id).rank!==r.rank)conflicts.add(id);else records.set(id,r);}
    const rankIds=new Map();
    for(const [id,r] of records)if(H.validRank(r.rank)&&!conflicts.has(id)){if(!rankIds.has(r.rank))rankIds.set(r.rank,[]);rankIds.get(r.rank).push(id);}
    for(const ids of rankIds.values())if(ids.length>1)ids.forEach(id=>conflicts.add(id));
    const valid=[...records].filter(([id,r])=>H.validRank(r.rank)&&!conflicts.has(id)).map(([id,r])=>({...r,id,type:classify(r).name,typeBasis:classify(r).basis})).sort((a,b)=>a.rank-b.rank||a.id.localeCompare(b.id));
    const top=valid.filter(r=>r.rank<=20),unknown=missingIds+[...records].filter(([id,r])=>!H.validRank(r.rank)||conflicts.has(id)).length;
    const contiguous=top.every((r,i)=>r.rank===i+1),complete=top.length===20||(unknown===0&&valid.length===top.length&&valid.length<20&&contiguous);
    for(const id of conflicts)records.delete(id);
    return {status:complete?'complete':'partial',complete,top,records,total:top.length,unknown};
  }
  function analyze(points){
    const known=points.filter(p=>p.count!=null),count=known.length;
    if(!count)return {count:0,peak:null,peakMonths:[],average:null,first:null,last:null,delta:null,status:'insufficient'};
    const peak=Math.max(...known.map(p=>p.count)),first=known[0],last=known.at(-1),delta=last.count-first.count,average=known.reduce((s,p)=>s+p.count,0)/count;
    const result={count,peak,peakMonths:known.filter(p=>p.count===peak).map(p=>p.month),average,first,last,delta,status:'insufficient',activeMonths:known.filter(p=>p.count>0).length};
    if(count<3||points.at(-1).count==null)return result;
    const meanX=known.reduce((s,p)=>s+Number(p.month.slice(5)),0)/count;
    const slope=known.reduce((s,p)=>s+(Number(p.month.slice(5))-meanX)*(p.count-average),0)/known.reduce((s,p)=>s+(Number(p.month.slice(5))-meanX)**2,0);
    const half=Math.floor(count/2),avg=ps=>ps.reduce((s,p)=>s+p.count,0)/ps.length,front=avg(known.slice(0,half)),back=avg(known.slice(-half));
    return {...result,slope,front,back,status:delta>0&&slope>0&&back>front?'up':delta<0&&slope<0&&back<front?'down':known.every(p=>p.count===first.count)?'stable':'mixed'};
  }
  function build(rows,{month,compareMonth='',category,metric,tasks=[]}){
    const year=month.slice(0,4),source=rows.filter(r=>r.kind==='product'&&r.category===category&&r.metric===metric);
    const relevantTasks=tasks.filter(t=>t.kind==='product'&&t.category===category),taskMap=new Map(relevantTasks.map(t=>[t.month,t]));
    const yearMonths=[...new Set([...source.map(r=>r.month),...relevantTasks.map(t=>t.month),month].filter(m=>m.startsWith(year+'-')))].sort();
    const months=Array.from({length:Number(yearMonths.at(-1).slice(5))},(_,i)=>year+'-'+String(i+1).padStart(2,'0'));
    const compareValid=!!compareMonth&&compareMonth<month,needed=new Set([...months,month,...(compareValid?[compareMonth]:[])]),byMonth=new Map([...needed].map(m=>[m,[]]));
    for(const r of source)if(needed.has(r.month))byMonth.get(r.month).push(r);
    const lists=new Map([...byMonth].map(([m,rs])=>[m,monthly(rs,taskMap.get(m))]));
    const current=lists.get(month),previous=compareValid?lists.get(compareMonth):null;
    const types=[...new Set([...lists.values()].flatMap(list=>list.top.map(r=>r.type)))];
    const count=(list,type)=>!list||!list.complete?null:list.top.filter(r=>r.type===type).length;
    const groups=types.map(name=>{
      const points=months.map(m=>({month:m,count:count(lists.get(m),name),observed:lists.get(m).top.filter(r=>r.type===name).length,status:lists.get(m).status}));
      const analysis=analyze(points),now=count(current,name),before=count(previous,name);
      const items=current.top.filter(r=>r.type===name).map(r=>{
        const old=previous?.records.get(r.id),oldRank=H.validRank(old?.rank)?old.rank:null;
        const isNew=!compareValid?null:oldRank!=null?oldRank>20:previous.complete?true:null;
        return {...r,oldRank,isNew,rankDelta:oldRank==null?null:oldRank-r.rank};
      }).sort((a,b)=>Number(b.isNew===true)-Number(a.isNew===true)||a.rank-b.rank);
      const shopMap=new Map();
      for(const r of [...items].sort((a,b)=>a.rank-b.rank)){
        const key=H.shopKey(r);if(!key)continue;
        if(!shopMap.has(key))shopMap.set(key,{key,name:r.shop_name,url:r.shop_url,ids:new Set()});
        const id=H.shopId(r);if(id)shopMap.get(key).ids.add(id);
      }
      const shops=[...shopMap.values()].map(({ids,...shop})=>({...shop,id:ids.size===1?[...ids][0]:''}));
      return {name,points,analysis,current:now,previous:before,delta:now==null||before==null?null:now-before,observed:items.length,items,shops};
    }).sort((a,b)=>Number(b.delta>0)-Number(a.delta>0)||(a.delta>0&&b.delta>0?b.delta-a.delta:0)||(b.current??b.observed)-(a.current??a.observed)||(b.analysis.average??0)-(a.analysis.average??0)||a.name.localeCompare(b.name));
    const rising=groups.filter(g=>g.analysis.status==='up').sort((a,b)=>b.analysis.delta-a.analysis.delta||b.analysis.average-a.analysis.average);
    const declining=groups.filter(g=>g.analysis.status==='down').sort((a,b)=>a.analysis.delta-b.analysis.delta);
    const common=groups.filter(g=>g.analysis.count>=3&&g.analysis.status!=='insufficient'&&g.analysis.status!=='down'&&g.analysis.average>=1&&g.analysis.activeMonths>=Math.ceil(g.analysis.count*.7)).sort((a,b)=>b.analysis.average-a.analysis.average);
    const opportunities=[...new Map([...rising.filter(g=>g.name!=='Other').slice(0,2),...common.filter(g=>g.name!=='Other')].map(g=>[g.name,g])).values()].slice(0,3);
    return {year,month,compareMonth,compareValid,months,groups,current,previous,rising,declining,common,opportunities,completeMonths:months.filter(m=>lists.get(m).complete).length};
  }
  return {classify,monthly,analyze,build};
});
