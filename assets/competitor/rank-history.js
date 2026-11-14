(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.RankHistory=api;
})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const validRank=n=>Number.isInteger(n)&&n>0;
  function shopKey(row){
    const url=String(row.shop_url||'').trim();
    if(/^https:\/\/shopee\.ph\//i.test(url))return url.split(/[?#]/)[0].replace(/\/+$/,'').toLowerCase();
    return row.kind==='shop'&&row.entity_id?'shop:'+row.entity_id:'';
  }
  function entityKey(row){return row.kind==='shop'?shopKey(row):String(row.item_id||row.entity_id||'');}
  function shopId(row){
    const product=String(row.product_url||'');
    if(/^https:\/\/shopee\.ph\//i.test(product)){
      const match=product.match(/-i\.(\d+)\.\d+(?:[/?#]|$)/)||product.match(/\/product\/(\d+)\/\d+(?:[/?#]|$)/);
      if(match)return match[1];
    }
    const match=String(row.shop_url||'').match(/^https:\/\/shopee\.ph\/shop\/(\d+)(?:[/?#]|$)/i);
    return match?match[1]:'';
  }
  function shops(rows){
    const stores=new Map();
    for(const row of rows){
      const key=shopKey(row);if(!key)continue;
      if(!stores.has(key))stores.set(key,{key,name:row.shop_name||row.brand||key,brand:row.brand||'',own:!!row.skintific,month:'',ids:new Set()});
      const store=stores.get(key),id=shopId(row);if(id)store.ids.add(id);
      if(row.month>=store.month){store.month=row.month;store.name=row.shop_name||store.name;store.brand=row.brand||store.brand;store.own=!!row.skintific;}
    }
    return [...stores.values()].map(({ids,...store})=>({...store,id:ids.size===1?[...ids][0]:''})).sort((a,b)=>a.name.localeCompare(b.name)||a.key.localeCompare(b.key));
  }
  function analyze(points){
    const known=points.map((p,i)=>({...p,x:Number(p.month.slice(5)),i})).filter(p=>validRank(p.rank));
    const ranks=known.map(p=>p.rank),count=known.length;
    const best=count?Math.min(...ranks):null,worst=count?Math.max(...ranks):null;
    const result={count,best,worst,bestMonths:known.filter(p=>p.rank===best).map(p=>p.month),worstMonths:known.filter(p=>p.rank===worst).map(p=>p.month),first:known[0]||null,last:known.at(-1)||null,delta:count?known[0].rank-known.at(-1).rank:null,status:'unknown'};
    if(!count)return result;
    if(count<3)return {...result,status:'insufficient'};
    if(!validRank(points.at(-1)?.rank))return {...result,status:'missing'};
    if(best===worst)return {...result,status:'stable',slope:0,front:best,back:best};
    // Use calendar spacing, not row positions; missing months are never interpolated.
    const meanX=known.reduce((s,p)=>s+p.x,0)/count,meanY=ranks.reduce((a,b)=>a+b,0)/count;
    const slope=known.reduce((s,p)=>s+(p.x-meanX)*(p.rank-meanY),0)/known.reduce((s,p)=>s+(p.x-meanX)**2,0);
    const half=Math.floor(count/2),avg=ps=>ps.reduce((s,p)=>s+p.rank,0)/ps.length;
    const front=avg(known.slice(0,half)),back=avg(known.slice(-half));
    const status=result.delta>0&&slope<0&&front>back?'up':result.delta<0&&slope>0&&front<back?'down':'mixed';
    return {...result,status,slope,front,back};
  }
  function build(rows,{kind,metric,months,categories,shop='',shops=null,tasks=[]}){
    const monthSet=new Set(months),catSet=new Set(categories),shopSet=shops==null?null:new Set(shops),groups=new Map();
    const coverage=new Map(tasks.filter(t=>t.kind===kind).map(t=>[JSON.stringify([t.category,t.month]),t.status]));
    for(const row of rows){
      if(row.kind!==kind||row.metric!==metric||!monthSet.has(row.month)||!catSet.has(row.category)||(shopSet?!shopSet.has(shopKey(row)):shop&&shopKey(row)!==shop))continue;
      const id=entityKey(row);if(!id)continue;
      const key=JSON.stringify([id,row.category]);
      if(!groups.has(key))groups.set(key,{id,category:row.category,kind,records:new Map(),sample:row});
      const group=groups.get(key),prev=group.records.get(row.month);
      if(!prev)group.records.set(row.month,{rank:validRank(row.rank)?row.rank:null,status:validRank(row.rank)?'ranked':'unranked'});
      else if(prev.rank!==(validRank(row.rank)?row.rank:null))group.records.set(row.month,{rank:null,status:'conflict'});
      if(row.month>=group.sample.month)group.sample={...row,image_url:row.image_url||group.sample.image_url,product_url:row.product_url||group.sample.product_url};
    }
    return [...groups.values()].map(group=>{
      const points=months.map(month=>{
        const record=group.records.get(month);if(record)return {month,...record};
        const status=coverage.get(JSON.stringify([group.category,month]));
        return {month,rank:null,status:status==='source_not_listed'?'no_list':status==='complete'?'absent':'not_imported'};
      });
      return {id:group.id,category:group.category,kind:group.kind,sample:group.sample,points,analysis:analyze(points)};
    }).sort((a,b)=>categories.indexOf(a.category)-categories.indexOf(b.category)||(a.points.at(-1).rank??Infinity)-(b.points.at(-1).rank??Infinity)||a.id.localeCompare(b.id));
  }
  return {validRank,shopKey,shopId,shops,entityKey,analyze,build};
});
