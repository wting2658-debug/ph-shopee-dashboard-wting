const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const payload=JSON.parse(html.match(/const PAYLOAD = (.*?);\r?\n/)[1]);
const supplemental=JSON.parse(fs.readFileSync(path.join(root,'assets/daily-report-data.json'),'utf8'));
// Use the actual shared aggregation helpers and report calculations.
const shared=html.match(/    const FACT = \{[\s\S]*?\n    \};/)[0]+
  html.slice(html.indexOf('    function createAgg()'),html.indexOf('    function getSelectedProductIds()'));
const code=fs.readFileSync(path.join(root,'assets/daily-report.js'),'utf8').split('// ===== Daily report rendering =====')[0];
const context=vm.createContext({assert,payload,supplemental});
vm.runInContext(shared+code+`
assert.deepEqual([...dpDates('2026-10-30','2026-11-02')],['2026-10-30','2026-10-31','2026-11-01','2026-11-02']);
assert.equal(dpPreviousDay('2026-03-31'),null);
assert.equal(dpPreviousDay('2026-01-15'),'2025-12-15');
assert.equal(dpPreviousDay('2024-03-29'),'2024-02-29');
assert.equal(dpRatio(0,100),0);
assert.equal(dpRatio(12,0),null);
assert.equal(dpRatio(undefined,100),null);
assert.equal(dpSum([1,null]),null);
assert.equal(dpChange(30,0),null);

const days=dpStoreDays(payload.facts),current=dpDates('2026-11-01','2026-11-15'),previous=dpDates('2026-10-01','2026-10-15');
const total=dpPeriod(current,days);
const raw=payload.facts.filter(r=>r[0]>='2026-11-01' && r[0]<='2026-11-15');
assert.ok(Math.abs(total.gmv-raw.reduce((s,r)=>s+r[2],0))<1e-6);
assert.ok(Math.abs(total.onsiteFee-raw.reduce((s,r)=>s+r[6],0)/total.gmv)<1e-12);
assert.ok(Math.abs(total.totalFee-(total.adSpend+total.metaSpend)/total.gmv)<1e-12);
assert.equal(dpPeriod(['2027-01-01'],days),null);
assert.equal(dpPeriod(['2026-11-15','2026-11-16'],days),null);
assert.equal(dpBuyerPeriod(current,supplemental.shop).newBuyers,12308);
assert.equal(dpBuyerPeriod(['2026-11-16'],supplemental.shop).newBuyers,null);

const af=dpAffiliatePeriod(current,previous,supplemental.affiliateCost,days);
assert.equal(af.dates.length,13);
assert.equal(af.dates.at(-1),'2026-11-13');
assert.equal(af.compareDates.at(-1),'2026-10-13');
assert.ok(Math.abs(af.current-af.dates.reduce((s,d)=>s+supplemental.affiliateCost[d],0)/af.dates.reduce((s,d)=>s+days.get(d).gmv,0))<1e-12);
assert.equal(dpAffiliatePeriod(['2026-11-15'],['2026-10-15'],supplemental.affiliateCost,days).current,null);

const dimension=new Map(payload.products.map(p=>[p.id,p])),top=dpTopTen(payload.facts,current,previous,dimension);
assert.equal(top.length,10);
assert.equal(new Set(top.map(r=>r.id)).size,10);
assert.equal(top[0].id,'蓝色气垫主链');
const independent=new Map();
for(const r of raw)if(dimension.get(r[1]).has_store)independent.set(r[1],(independent.get(r[1])||0)+r[2]);
assert.deepEqual([...top.map(r=>r.id)].sort(),[...independent].sort((a,b)=>b[1]-a[1]).slice(0,10).map(r=>r[0]).sort());
for(const r of top)assert.ok(Math.abs(r.current.gmv-independent.get(r.id))<1e-6);
consoleResult={sales:total.gmv,newBuyers:dpBuyerPeriod(current,supplemental.shop).newBuyers,affiliateRate:af.current,top10:top.map(r=>r.id)};
`,context);
console.log('Daily report calculations passed:',context.consoleResult);
// Compile every inline script; catch errors after the HTML injection as well.
for(const [,script] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(script);
