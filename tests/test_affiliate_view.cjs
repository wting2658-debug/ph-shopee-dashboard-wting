const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const data = {
  products:[['a','cream','Cream'],['b','makeup','Cushion']],channels:['Live','Video'],
  dates:['2026-01-01','2026-01-03'],
  rows:[[0,0,0,100,10,3,2],[0,0,1,200,0,5,4],[0,1,0,400,10,6,5],[1,1,1,50,5,1,1]],
  shop_gmv:{'2026-01-01':999,'2026-01-03':900},shop:{'2026-01-01':[700,20,14,8]}
};
const nodes=new Map(), node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',addEventListener(){}});return nodes.get(id);};
const charts=new Map();
const frames=[];
const context=vm.createContext({
  data, Map, Set, console,
  PAYLOAD:{facts:[['2026-01-01','a',600],['2026-01-01','b',400]],generated_at:'today'},FACT:{date:0,gmv:2},
  document:{getElementById:node,querySelector:node}, location:{hash:''},
  state:{activePage:'affiliate',start:'2026-01-01',end:'2026-01-03',compareStart:'2025-12-01',compareEnd:'2025-12-03'},
  shiftMonth:(d,m)=>{const date=new Date(d+'T00:00:00Z'); const day=date.getUTCDate();date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+m);const last=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();date.setUTCDate(Math.min(day,last));return date.toISOString().slice(0,10);},upsertChart:(id,c)=>charts.set(id,c),requestAnimationFrame:callback=>frames.push(callback),
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/affiliate.js'),'utf8'),context);
const run=s=>vm.runInContext(s,context);
assert.equal(run("afAggregate(data,'2026-01-01','2026-01-01').roi"),35); // Weighted totals, not the average of row ROI.
assert.equal(run("afAggregate(data,'2026-01-01','2026-01-01',{product:'a',channel:'Video'}).roi"),null);
assert.equal(run("afAggregate(data,'2026-01-01','2026-01-01',{category:'cream'}).gmv"),300);
assert.equal(run("afAggregate(data,'2026-01-01','2026-01-01',{product:'a',channel:'Live'}).gmv"),100);
assert.equal(run("afAggregate(data,'2026-01-01','2026-01-03').complete"),false);
assert.equal(run("afAggregate(data,'2026-01-02','2026-01-02').gmv"),null);
assert.equal(run("afAggregate(data,'2026-01-03','2026-01-03',{product:'a'}).gmv"),0); // Known day, no sales for selected product.
assert.equal(run("afStoreTotals(data,['2026-01-01','2026-01-03'],AF_STORE_GMV)"),1900); // Full shop, historical fallback once per day.
assert.equal(run("afStoreTotals(data,['2026-01-01','2026-01-02'],AF_STORE_GMV)"),null);
assert.equal(run("afShopTotals(data,['2026-01-01']).orders"),8); // Product orders are 11; store report is 8.
assert.equal(run("afShopTotals(data,['2026-01-01','2026-01-03']).orders"),null);
assert.equal(run("afGroups(data,afAggregate(data,'2026-01-02','2026-01-02'),afAggregate(data,'2026-01-01','2026-01-01'),'product').length"),0);
run("AF_STORE_GMV.set('2026-01-02',250); AF_STORE_GMV.set('2025-12-01',800); AF_STORE_GMV.set('2025-12-02',200); AF_STORE_GMV.set('2025-12-03',900)");
run("AFFILIATE_DATA={...data,schema:1,coverage:{start:'2026-01-01',end:'2026-01-03',days:2},source:'source',shop_source:'shop',audit:{shop_reconciliation_differences:[]}}; renderAffiliatePage()");
assert.deepEqual(Array.from(charts.get('chart-af-gmv').data.datasets[1].data),[700,null,50]);
assert.match(node('af-kpis').innerHTML,/暂无可比数据/);
assert.match(node('af-kpis').innerHTML,/未跨品去重/);
run("AF_STATE.product='a'; AF_STATE.channel='Live'; renderAffiliatePage()");
assert.match(node('af-kpis').innerHTML,/¥100</);
const metric=key=>node('af-kpis').innerHTML.match(new RegExp(`data-af-metric="${key}"[\\s\\S]*?</article>`))[0];
assert.match(metric('store'),/¥2,150</); // Include store GMV on the missing affiliate day, independent of product filters.
assert.match(metric('store'),/¥1,900</); // Store comparison still works when affiliate comparison is incomplete.
assert.match(metric('share'),/af-value">—</); // Never divide a partial affiliate period by a full store period.
run("AF_STORE_GMV.set('2026-01-04',400); state.end='2026-01-04'; renderAffiliatePage()");
assert.equal(run('afRanges().end'),'2026-01-04'); // Affiliate coverage ends on the 3rd; shared query still ends on the 4th.
assert.match(metric('store'),/¥2,550</);
assert.match(metric('store'),/2026-01-01 → 2026-01-04/);
assert.match(node('af-status').innerHTML,/联盟统计 2026-01-01 → 2026-01-03/);
assert.deepEqual(Array.from(charts.get('chart-af-gmv').data.datasets[1].data),[100,null,0,null]);
run("state.end='2026-01-01'; renderAffiliatePage()");
assert.match(metric('share'),/10\.00%/); // A fully covered period still shows the selected product's share of full-store GMV.
run("state.end='2026-01-03'");
run("AF_STATE.compare='custom';AF_STATE.day='2026-01-03'");
assert.equal(run('afRanges().start'),'2026-01-03');
assert.equal(run('afRanges().previousStart'),'2025-12-01');
run("AF_STATE.day='';AF_STATE.product='';AF_STATE.channel='';renderAffiliatePage()");
charts.get('chart-af-gmv').options.onClick({},[{index:0}]);
assert.equal(run('AF_STATE.day'),''); // Redraw must wait until Chart.js finishes dispatching the click.
frames.shift()();
assert.equal(run('AF_STATE.day'),'2026-01-01');

// Regression for the user's preview: Nov 1–14 must use the full Store Analysis
// period even while affiliate product data ends on Nov 13.
const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const payload=JSON.parse(html.match(/const PAYLOAD = (.*?);\r?\n/)[1]);
const actual=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/affiliate-data.json'),'utf8'));
context.actual=actual;
context.actualFacts=payload.facts;
run("AF_STORE_GMV.clear(); for(const row of actualFacts) AF_STORE_GMV.set(row[0],(AF_STORE_GMV.get(row[0])||0)+row[2]); AFFILIATE_DATA=actual; Object.assign(state,{start:'2026-11-01',end:'2026-11-14',compareStart:'2026-10-01',compareEnd:'2026-10-14'}); Object.assign(AF_STATE,{day:'',product:'',category:'',channel:'',compare:'month'}); renderAffiliatePage()");
const storeExpected=payload.facts.filter(r=>r[0]>='2026-11-01'&&r[0]<='2026-11-14').reduce((sum,r)=>sum+r[2],0);
assert.equal(Math.round(storeExpected),1993015);
assert.match(metric('store'),/¥1,993,015</);
assert.match(metric('store'),/2026-11-01 → 2026-11-14/);
assert.match(metric('gmv'),/¥643,652</);
assert.match(metric('gmv'),/2026-11-01 → 2026-11-13/);
assert.match(metric('gmv'),/¥563,842</);
assert.match(metric('gmv'),/↑ 14\.2%/);
assert.match(metric('share'),/33\.97%/);
assert.match(metric('share'),/同期全店 ¥1,894,935/);
assert.match(node('af-table-period').textContent,/2026-11-01 → 2026-11-13.*2026-10-01 → 2026-10-13/);
assert.doesNotMatch(node('af-category-rows').innerHTML,/暂无可比数据/);
assert.doesNotMatch(node('af-product-rows').innerHTML,/暂无可比数据/);
// Independently total the source asset's current/previous rows and verify every
// rendered category and product, including products present only last period.
const controls={current:{gmv:0,cost:0,units:0,orders:0},previous:{gmv:0,cost:0,units:0,orders:0}};
const groups={category:new Map(),product:new Map()};
for(const row of actual.rows){
  const date=actual.dates[row[0]],side=date>='2026-11-01'&&date<='2026-11-13'?'current':date>='2026-10-01'&&date<='2026-10-13'?'previous':null;
  if(!side)continue;
  ['gmv','cost','units','orders'].forEach((key,i)=>controls[side][key]+=row[3+i]);
  const product=actual.products[row[1]];
  for(const [dimension,key] of [['category',product[1]],['product',product[0]]]){
    if(!groups[dimension].has(key))groups[dimension].set(key,{current:0,previous:0});
    groups[dimension].get(key)[side]+=row[3];
  }
}
controls.current.roi=controls.current.gmv/controls.current.cost;
controls.previous.roi=controls.previous.gmv/controls.previous.cost;
controls.current.commissionRate=controls.current.cost/controls.current.gmv;
controls.previous.commissionRate=controls.previous.cost/controls.previous.gmv;
for(const key of ['gmv','cost','units','orders','roi','commissionRate']){
  const decimals=key==='roi'||key==='commissionRate'?2:0;
  const format=value=>(key==='commissionRate'?value*100:value).toLocaleString('zh-CN',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
  assert.ok(metric(key).includes(format(controls.current[key])));
  assert.ok(metric(key).includes(format(controls.previous[key])));
  const percent=Math.abs((controls.current[key]-controls.previous[key])/controls.previous[key]*100).toLocaleString('zh-CN',{minimumFractionDigits:1,maximumFractionDigits:1});
  assert.ok(metric(key).includes(percent+'%'));
}
for(const key of ['gmv','cost','units','orders','roi','commissionRate','share'])assert.doesNotMatch(metric(key),/暂无可比数据/);
const trend=charts.get('chart-af-gmv'),costTrend=charts.get('chart-af-cost');
assert.equal(trend.data.datasets.length,6);
assert.equal(costTrend.data.datasets.length,4);
const sum=values=>values.reduce((total,value)=>total+(value??0),0);
assert.ok(Math.abs(sum(trend.data.datasets[0].data)-storeExpected)<1e-6);
assert.ok(Math.abs(sum(trend.data.datasets[1].data)-controls.current.gmv)<1e-6);
assert.ok(Math.abs(sum(trend.data.datasets[4].data.slice(0,13))-controls.previous.gmv)<1e-6);
assert.ok(Math.abs(sum(costTrend.data.datasets[0].data)-controls.current.cost)<1e-6);
assert.ok(Math.abs(sum(costTrend.data.datasets[2].data.slice(0,13))-controls.previous.cost)<1e-6);
assert.equal(trend.data.datasets[1].data[13],null); // Nov 14 is missing; do not invent zero.
assert.ok(trend.data.datasets[4].data[13]>0); // Oct 14 exists and remains visible as a comparison point.
assert.deepEqual(Array.from(trend.data.datasets[4].borderDash),[6,4]);
assert.deepEqual(Array.from(trend.data.datasets[1].borderDash),[]);
assert.match(trend.options.plugins.tooltip.callbacks.title([{dataIndex:0}]),/2026-11-01.*2026-10-01/);
assert.match(trend.options.plugins.tooltip.callbacks.label({dataset:trend.data.datasets[4],dataIndex:0,raw:trend.data.datasets[4].data[0]}),/联盟 GMV · 上期（2026-10-01）/);
assert.match(node('af-gmv-trend-period').textContent,/2026-11-01 → 2026-11-14.*2026-10-01 → 2026-10-14/);
for(const [dimension,expected] of Object.entries(groups)){
  const rows=run(`afGroups(AFFILIATE_DATA,afAggregate(AFFILIATE_DATA,'2026-11-01','2026-11-13'),afAggregate(AFFILIATE_DATA,'2026-10-01','2026-10-13'),'${dimension}')`);
  assert.equal(rows.length,expected.size);
  for(const row of rows){
    const control=expected.get(row.key);
    assert.ok(Math.abs(row.gmv-control.current)<1e-6);
    assert.ok(Math.abs(row.previous-control.previous)<1e-6);
    const rendered=node(dimension==='category'?'af-category-rows':'af-product-rows').innerHTML.split('<tr').find(r=>r.includes(`data-af-key="${row.key}"`));
    assert.ok(rendered,`Missing ${dimension} ${row.key}`);
    if(control.previous){const change=(control.current-control.previous)/Math.abs(control.previous);assert.ok(rendered.includes(Math.abs(change*100).toLocaleString('zh-CN',{maximumFractionDigits:1,minimumFractionDigits:1})+'%'));}
    else assert.match(rendered,control.current?/上期为 0/:/0\.0%/);
  }
}
// An explicit custom comparison must remain as selected, and genuinely missing
// previous data must still be shown as unavailable instead of invented zeros.
run("AF_STATE.compare='custom';state.compareEnd='2026-10-14';renderAffiliatePage()");
assert.match(metric('gmv'),/对比 2026-10-01 → 2026-10-14/);
assert.doesNotMatch(metric('gmv'),/暂无可比数据/);
run("AF_STATE.product='28093494913';AF_STATE.channel='Shopee Video';state.compareEnd='2026-10-20';renderAffiliatePage()");
const filteredTrend=charts.get('chart-af-gmv');
assert.equal(filteredTrend.data.labels.length,20);
assert.equal(filteredTrend.data.datasets[1].data[14],null); // Comparison-only days must not repeat current values.
assert.equal(filteredTrend.data.datasets[4].afDates[19],'2026-10-20');
assert.match(filteredTrend.options.plugins.tooltip.callbacks.title([{dataIndex:19}]),/无对应日期.*2026-10-20/);
assert.equal(Math.round(sum(filteredTrend.data.datasets[0].data)),1993015); // Full shop remains unfiltered.
const filteredRaw=actual.rows.filter(r=>actual.products[r[1]][0]==='28093494913'&&actual.channels[r[2]]==='Shopee Video');
for(const [index,start,end] of [[1,'2026-11-01','2026-11-14'],[4,'2026-10-01','2026-10-20']]){
  const expected=filteredRaw.filter(r=>actual.dates[r[0]]>=start&&actual.dates[r[0]]<=end).reduce((total,r)=>total+r[3],0);
  assert.ok(Math.abs(sum(filteredTrend.data.datasets[index].data)-expected)<1e-6);
}
run("AF_STATE.product='';AF_STATE.channel=''");
run("state.compareStart='2025-01-01';state.compareEnd='2025-01-13';renderAffiliatePage()");
assert.match(metric('gmv'),/暂无可比数据/);
assert.ok(charts.get('chart-af-gmv').data.datasets[4].data.every(value=>value===null));
run("AF_STATE.compare='month'");
run("state.end='2026-11-13'; renderAffiliatePage()");
assert.match(metric('store'),/¥1,894,935</);
assert.match(metric('share'),/33\.97%/);
console.log('Affiliate filters, weighted ROI, order grain, daily gaps and full-shop denominator: OK');
