const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const source = html.split('// ===== Subsidy Page Rendering =====')[1].split('// ===== End Subsidy Page Rendering =====')[0];
const data = JSON.parse(fs.readFileSync(path.join(root, 'subsidy_data.json'), 'utf8'));
const nodes = new Map(), charts = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML:'', textContent:'', addEventListener(){}});
  return nodes.get(id);
};
const context = vm.createContext({document:{getElementById:node}, location:{hash:''},
  upsertChart:(id, config) => charts.set(id, config)});
vm.runInContext(source + '\nrenderSubsidyRollup();', context);
const latest = data.monthly_rollup.at(-1);
const previousRows = data.daily.filter(r => r.date.startsWith(latest.previous_month));
for (const channel of ['tt','sp']) {
  const chart = charts.get(`chart-subsidy-rollup-${channel}`);
  const previous = chart.data.datasets[1].data;
  assert.equal(previous.filter(v=>v!==null).length, previousRows.length);
  assert.deepEqual(Array.from(previous).filter(v=>v!==null), previousRows.map(r=>r[`${channel}_gmv`]));
  assert.deepEqual(Array.from(chart.data.datasets[3].data).filter(v=>v!==null), previousRows.map(r=>r[`${channel}_subsidy`]));
  assert.ok(node('subsidy-rollup').innerHTML.includes(latest[`previous_same_${channel}_gmv`].toLocaleString('en-US')));
}
assert.ok(node('subsidy-rollup-range').textContent.includes(latest.previous_same_end));
assert.ok(node('subsidy-rollup-source').innerHTML.includes('上月同期累计'));
console.log(`KPI cutoff ${latest.end} vs ${latest.previous_same_end}; full previous-month chart: OK`);
