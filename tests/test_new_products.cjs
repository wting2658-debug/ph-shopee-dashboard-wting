const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('assets/new-products.js','utf8').split('// ===== End new products calculation helpers =====')[0];
const context=vm.createContext({});
vm.runInContext(code+';globalThis.helpers={npWindow,npAggregate,npMatches,npRatio,npShipmentTotals,NP_TREND_METRICS,npTrendValue};',context);
const {npWindow,npAggregate,npMatches,npRatio,npShipmentTotals,NP_TREND_METRICS,npTrendValue}=context.helpers;
const p={id:'123',name:'新品',launch:'2026-05-15',rows:[
 {date:'2026-05-14',sales:999,impressions:100,clicks:10},
 {date:'2026-05-15',sales:100,units:2,orders:2,impressions:100,clicks:10,onSpend:10,onGmv:50,metaSpend:10,metaGmv:20,ttQty:2,shopeeQty:5,lazadaQty:3},
 {date:'2026-05-16',sales:200,units:4,orders:2,impressions:300,clicks:20,onSpend:20,onGmv:50,metaSpend:10,metaGmv:40,ttQty:0,shopeeQty:0,lazadaQty:0}
]};
let a=npAggregate(p,'2026-05-15','2026-05-16');
assert.equal(a.sales,300);assert.equal(a.units,6);assert.equal(a.ctr,30/400);assert.equal(a.cvr,4/30);
assert.equal(a.onRoi,100/30);assert.equal(a.metaRoi,3);assert.equal(a.fullRoi,6);
assert.equal(a.ttQty,2);assert.equal(a.shopeeQty,5);assert.equal(a.lazadaQty,3);
assert.equal(npAggregate(p,'2026-05-13','2026-05-14').counts.impressions,1);
assert.equal(npAggregate(p,'2026-05-15','2026-05-17').fullRoi,null);
assert.equal(npAggregate(p,'2026-05-17','2026-05-17').sales,null);
assert.equal(npAggregate(p,'2026-05-17','2026-05-16').sales,null);
const pre=npAggregate(p,'2026-05-08','2026-05-14');
assert.equal(pre.rows.length,7);assert.equal(pre.rows[0].date,'2026-05-08');assert.equal(pre.rows[6].date,'2026-05-14');
assert.equal(pre.sales,999);assert.equal(pre.counts.impressions,1);
assert.equal(pre.rows[0].impressions,undefined);assert.equal(npRatio(pre.rows[0].clicks,pre.rows[0].impressions),null);
assert.equal(npRatio(pre.rows[6].clicks,pre.rows[6].impressions),0.1);
assert.equal(npRatio(0,100),0);assert.equal(npRatio(0,0),null);
assert.equal(npMatches(p,{launchYear:'2026',launchMonth:'05',search:'123'}),true);
assert.equal(npMatches(p,{launchYear:'2026',launchMonth:'04'}),false);
const d={coverage:{performance:{end:'2026-11-15'}},cutoff:'2026-11-15'};
let w=npWindow(p,{mode:'month',year:'2026',month:'05'},d);assert.equal(w.start,'2026-05-15');assert.equal(w.end,'2026-05-31');
w=npWindow(p,{mode:'year',year:'2026'},d);assert.equal(w.start,'2026-05-15');assert.equal(w.end,'2026-11-15');
w=npWindow({...p,launch:'2025-01-01'},{mode:'month',year:'2026',month:'02'},d);assert.equal(w.end,'2026-02-28');
w=npWindow({...p,launch:'2024-01-01'},{mode:'month',year:'2024',month:'02'},d);assert.equal(w.end,'2024-02-29');
w=npWindow({...p,launch:'2025-01-01'},{mode:'year',year:'2025'},d);assert.equal(w.end,'2025-12-31');
assert.equal(npAggregate(p,'2026-05-16','2026-05-16').shopeeQty,0);
assert.equal(npShipmentTotals(p.rows[1]).gap,-3);assert.equal(npShipmentTotals(p.rows[1]).total,10);
assert.equal(npShipmentTotals(p.rows[2]).gap,0);assert.equal(npShipmentTotals(p.rows[2]).total,0);
assert.equal(npShipmentTotals({ttQty:9,shopeeQty:5,lazadaQty:null}).gap,4);
assert.equal(npShipmentTotals({ttQty:9,shopeeQty:5,lazadaQty:null}).total,null);
assert.equal(npShipmentTotals({ttQty:null,shopeeQty:5,lazadaQty:3}).gap,null);
const trendRow={sales:200,orders:3,units:7,impressions:1000,clicks:40,onGmv:40,onSpend:8,metaGmv:60,metaSpend:12};
assert.equal(NP_TREND_METRICS.length,14);assert.equal(new Set(NP_TREND_METRICS.map(metric=>metric.key)).size,14);
for (const key of ['sales','orders','impressions','clicks','onGmv','onSpend','metaGmv','metaSpend']) assert.equal(npTrendValue(trendRow,key),trendRow[key]);
assert.equal(npTrendValue(trendRow,'ctr'),0.04);assert.equal(npTrendValue(trendRow,'cvr'),3/40);
assert.equal(npTrendValue(trendRow,'onFee'),0.04);assert.equal(npTrendValue(trendRow,'metaFee'),0.06);
assert.equal(npTrendValue(trendRow,'onRoi'),5);assert.equal(npTrendValue(trendRow,'metaRoi'),5);
for (const metric of NP_TREND_METRICS) assert.equal(npTrendValue({},metric.key),null);
assert.equal(npTrendValue({sales:200,onSpend:0},'onFee'),0);
assert.equal(npTrendValue({sales:0,onSpend:8},'onFee'),null);
assert.equal(npTrendValue({onGmv:0,onSpend:0},'onRoi'),null);
console.log('New product period, rates, ROI coverage, cohort filters and shipment checks passed.');
