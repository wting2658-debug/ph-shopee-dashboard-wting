const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../functions/refresh-data.js'), 'utf8').replaceAll('export async function', 'async function');
const now = Date.parse('2026-11-17T02:05:00Z');
const apiBase = 'https://api.github.com/repos/wting2658-debug/ph-shopee-dashboard-wting';
const oldRun = { id: 99, event: 'workflow_dispatch', status: 'completed', conclusion: 'success', created_at: new Date(now - 30000).toISOString() };
const refresh = { id: 101, head_branch: 'main', path: '.github/workflows/refresh-dashboard.yml', event: 'workflow_dispatch', status: 'completed', conclusion: 'success', created_at: new Date(now - 60000).toISOString(), updated_at: new Date(now - 20000).toISOString(), html_url: 'https://github.com/example/refresh/101' };
const deployment = { id: 202, event: 'workflow_run', display_title: 'Refresh 101', head_sha: 'current-sha', status: 'completed', conclusion: 'success', created_at: new Date(now - 10000).toISOString(), html_url: 'https://github.com/example/deploy/202' };
let assertions = 0;

function harness(handler) {
  const calls = [];
  const FixedDate = class extends Date { static now() { return now; } };
  const scope = { Response, URL, URLSearchParams, Date: FixedDate, fetch: async (url, options = {}) => {
    calls.push({ url, options });
    const value = handler(url, options);
    return value instanceof Response ? value : new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }};
  vm.runInNewContext(source + '\nthis.handlers = { onRequestPost, onRequestGet };', scope);
  const context = (query = '', key = 'secret') => ({ env: { GITHUB_ACTIONS_TOKEN: 'github-token', REFRESH_KEY: 'secret' }, request: new Request('https://dashboard.example/refresh-data' + query, { headers: { 'X-Refresh-Key': key } }) });
  return { calls, context, ...scope.handlers };
}
function refreshHandler(runs = [], deployments = [], options = {}) {
  return (url, request) => {
    if (url.includes('/dispatches')) return new Response(null, { status: 204 });
    if (url.includes('/actions/runs/101')) return options.refresh || refresh;
    if (url.includes('/workflows/refresh-dashboard.yml/runs')) return { workflow_runs: runs };
    if (url.includes('/workflows/deploy-dashboard.yml/runs')) return { workflow_runs: deployments };
    if (url.endsWith('/git/ref/heads/main')) return { object: { sha: 'current-sha' } };
    throw new Error('Unexpected API ' + url);
  };
}
async function check(name, callback) { await callback(); assertions++; console.log('PASS', name); }
async function main() {
  await check('wrong refresh password cannot read or start jobs', async () => {
    const h = harness(() => { throw new Error('Must not call GitHub'); });
    assert.equal((await h.onRequestPost(h.context('', 'wrong'))).status, 401);
    assert.equal((await h.onRequestGet(h.context('?job_id=' + now, 'wrong'))).status, 401);
    assert.equal(h.calls.length, 0);
  });
  for (const conclusion of ['success', 'failure']) {
    await check('recent completed ' + conclusion + ' starts a fresh download', async () => {
      const h = harness(refreshHandler([{ ...oldRun, conclusion }]));
      const response = await h.onRequestPost(h.context());
      const data = await response.json();
      assert.equal(response.status, 202); assert.equal(data.after_run_id, '99');
      assert.equal(data.status, 'downloading'); assert.equal(data.reused, undefined);
      assert.equal(h.calls.filter(c => c.options.method === 'POST').length, 1);
      assert.deepEqual(JSON.parse(h.calls[1].options.body), { ref: 'main' });
    });
  }
  await check('active scheduled job is reused and duplicate dispatch is avoided', async () => {
    const h = harness(refreshHandler([{ ...refresh, event: 'schedule', status: 'in_progress', conclusion: null }]));
    const data = await (await h.onRequestPost(h.context())).json();
    assert.equal(data.run_id, '101'); assert.equal(data.reused, true); assert.equal(data.status, 'processing');
    assert.equal(h.calls.length, 1); assert.ok(!h.calls[0].url.includes('event=workflow_dispatch'));
  });
  await check('same-second completed run cannot be mistaken for the newly dispatched run', async () => {
    const time = Math.floor(now / 1000) * 1000;
    const h = harness(refreshHandler([{ ...refresh, id: 99, created_at: new Date(time).toISOString() }, { ...refresh, status: 'queued', id: 101, created_at: new Date(time).toISOString() }]));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&after_run_id=99`))).json();
    assert.equal(data.run_id, '101'); assert.equal(data.status, 'downloading');
  });
  await check('missing job waits briefly and then reports dispatch timeout', async () => {
    const h = harness(refreshHandler());
    assert.equal((await (await h.onRequestGet(h.context(`?job_id=${now}`))).json()).status, 'downloading');
    assert.equal((await (await h.onRequestGet(h.context(`?job_id=${now - 121000}`))).json()).status, 'error');
  });
  await check('invalid or missing job identifiers are rejected before GitHub requests', async () => {
    const h = harness(() => { throw new Error('Must not call GitHub'); });
    for (const query of ['', '?job_id=0', '?job_id=invalid', `?job_id=${now}&run_id=abc`, `?job_id=${now}&after_run_id=abc`])
      assert.equal((await h.onRequestGet(h.context(query))).status, 400);
    assert.equal(h.calls.length, 0);
  });
  await check('run id must belong to main dashboard refresh workflow', async () => {
    const h = harness(refreshHandler([], [], { refresh: { ...refresh, path: '.github/workflows/another.yml' } }));
    assert.equal((await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).status, 400);
  });
  for (const state of ['queued', 'in_progress']) {
    await check('running build remains ' + state, async () => {
      const h = harness(refreshHandler([], [], { refresh: { ...refresh, status: state, conclusion: null } }));
      const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
      assert.equal(data.status, state === 'queued' ? 'downloading' : 'processing'); assert.equal(h.calls.length, 1);
    });
  }
  await check('failed build reports failure without calling deployment APIs', async () => {
    const h = harness(refreshHandler([], [], { refresh: { ...refresh, conclusion: 'failure' } }));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
    assert.equal(data.status, 'error'); assert.match(data.error, /数据刷新失败/); assert.equal(h.calls.length, 1);
  });
  await check('successful build does not complete before deployment exists', async () => {
    const h = harness(refreshHandler([], []));
    assert.equal((await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json()).status, 'publishing');
  });
  await check('unrelated deployment and stale main revision do not satisfy current refresh', async () => {
    const h = harness(refreshHandler([], [{ ...deployment, display_title: 'Refresh 100' }, { ...deployment, head_sha: 'old-sha' }]));
    assert.equal((await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json()).status, 'publishing');
  });
  await check('active matching deployment reports publishing', async () => {
    const h = harness(refreshHandler([], [{ ...deployment, status: 'in_progress', conclusion: null }]));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
    assert.equal(data.status, 'publishing'); assert.equal(data.deploy_run_id, '202');
  });
  await check('failed matching deployment reports an error', async () => {
    const h = harness(refreshHandler([], [{ ...deployment, conclusion: 'failure' }]));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
    assert.equal(data.status, 'error'); assert.match(data.error, /线上部署失败/);
  });
  await check('complete is returned only after corresponding deployment succeeded on latest main', async () => {
    const h = harness(refreshHandler([], [deployment]));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
    assert.equal(data.status, 'complete'); assert.equal(data.run_id, '101'); assert.equal(data.deploy_run_id, '202');
    assert.ok(h.calls.some(c => c.url.endsWith('/git/ref/heads/main')));
  });
  await check('missing deployment eventually gives actionable timeout rather than false complete', async () => {
    const h = harness(refreshHandler([], [], { refresh: { ...refresh, updated_at: new Date(now - 601000).toISOString() } }));
    const data = await (await h.onRequestGet(h.context(`?job_id=${now}&run_id=101`))).json();
    assert.equal(data.status, 'error'); assert.match(data.error, /线上部署未启动/);
  });
  await check('GitHub network failures return a retryable service error', async () => {
    const h = harness(() => { throw new Error('GitHub unavailable'); });
    assert.equal((await h.onRequestPost(h.context())).status, 502);
  });
  console.log(`Manual refresh endpoint: ${assertions} scenarios passed`);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
