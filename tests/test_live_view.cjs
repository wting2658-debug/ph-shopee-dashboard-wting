// Exercise different source cutoffs and authoritative store totals together.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const nodes = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML:'',textContent:'',value:'',addEventListener(){}});
  return nodes.get(id);
};
const context = vm.createContext({
  PAYLOAD: {
    facts:[['2026-10-01','a',200],['2026-10-02','a',100],['2026-11-01','a',100],['2026-11-01','b',23],['2026-11-02','a',50]],
    available_range:{start:'2026-10-01',end:'2026-11-02'},source_urls:{store:'https://example.com/store'}
  },
  FACT:{date:0,gmv:2},
  LIVE_DATA:{
    daily:[{date:'2026-11-01',shop_gmv:999},{date:'2025-07-01',shop_gmv:77.3}],
    sessions:[{id:'1',name:'prior',date:'2026-10-01',start:'2026-10-01T12:00:00',end:'2026-10-01T13:00:00',gmv:30,hours:1,likes:2,buyers:1},{id:'2',name:'current',date:'2026-11-01',start:'2026-11-01T12:00:00',end:'2026-11-01T13:00:00',gmv:12.3,hours:1,likes:3,buyers:2}],
    coverage:{shop_start:'2025-07-01',shop_end:'2026-11-02',sessions_start:'2026-10-01',sessions_end:'2026-11-01'},sources:{daily:'daily',sessions:'sessions'}
  },
  state:{start:'2026-11-01',end:'2026-11-02',compareStart:'2026-10-01',compareEnd:'2026-10-02'},
  document:{getElementById:node}, location:{hash:''},upsertChart(){},
  shiftMonth:(date, months) => {const d=new Date(`${date}T00:00:00Z`);d.setUTCMonth(d.getUTCMonth()+months);return d.toISOString().slice(0,10);}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/live.js'),'utf8'),context);
const run = source => vm.runInContext(source,context);
assert.equal(run("liveDay('2026-11-01').shop_gmv"),123);
assert.equal(run("liveDay('2025-07-01').shop_gmv"),77.3);
run('renderLivePage()');
assert.match(node('live-kpis').innerHTML,/¥173</);
assert.match(node('live-kpis').innerHTML,/上月同期 ¥300</);
assert.match(node('live-kpis').innerHTML,/10\.00%/);
assert.match(node('live-coverage').innerHTML,/¥12 ÷ ¥123/);
assert.equal(run("liveDay('2026-11-02').gmv"),null);
run("LIVE_STATE.date='2025-07-01'; state.start='2026-11-02'; renderLivePage()");
assert.match(node('live-kpis').innerHTML,/¥50</);
assert.match(node('live-coverage').innerHTML,/暂无直播明细/);
assert.equal(node('live-detail-date').value,'2025-07-01');
run("LIVE_STATE.date='2026-11-02'; renderLiveDay()");
assert.match(node('live-day-kpis').innerHTML,/直播场次<\/span><strong>—/);
assert.match(node('live-day-kpis').innerHTML,/¥50</);
console.log('Store source, complete query range, matched share denominator, missing live data, historical dates: OK');
