/* Load monthly assets only after opening the competitor tab. */
(() => {
  'use strict';
  const embedded = new URLSearchParams(location.search).get('embedded') === '1';
  document.documentElement.classList.toggle('embedded', embedded);
  const status = document.getElementById('competitor-loading-text');
  const scripts = [
    'rank-history.js', 'rising-competitors.js', 'product-opportunities.js',
    'self-ranking.js', 'category-picker.js', 'app.js', 'rank-history-view.js',
    'rising-competitors-view.js', 'product-opportunities-view.js', 'self-ranking-view.js',
    '../competitor-bridge.js',
  ];
  async function readJson(path, digest) {
    if (!/^(manifest\.json|data\/[\w.-]+\.json)$/.test(path)) throw new Error('Invalid asset path');
    const response = await fetch(path, {cache:path === 'manifest.json' ? 'no-cache' : 'default'});
    if (!response.ok) throw new Error('Data request failed: ' + response.status);
    const bytes = await response.arrayBuffer();
    if (digest) {
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      const actual = Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2,'0')).join('');
      if (actual !== digest) throw new Error('Data hash mismatch');
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function unpack(chunk) {
    if (chunk.format !== 'ph-ranking-columns-v1') throw new Error('Unsupported data format');
    return chunk.rows.map(cells => {
      if (cells.length > chunk.columns.length) throw new Error('Invalid row schema');
      const row = {};
      cells.forEach((value, index) => {
        const key = chunk.columns[index], dictionary = chunk.dictionaries[key];
        if (dictionary && value !== null) {
          if (!Number.isInteger(value) || value < 0 || value >= dictionary.length) throw new Error('Invalid dictionary index');
          row[key] = dictionary[value];
        } else row[key] = value;
      });
      return row;
    });
  }
  async function start() {
    const manifest = await readJson('manifest.json');
    if (manifest.format !== 'ph-competitor-manifest-v1' || !manifest.chunks.length) throw new Error('Invalid manifest');
    let next = 0, completed = 0;
    const parts = new Array(manifest.chunks.length);
    await Promise.all(Array.from({length:Math.min(4,manifest.chunks.length)}, async () => {
      while (next < manifest.chunks.length) {
        const index = next++, entry = manifest.chunks[index];
        const rows = unpack(await readJson(entry.file, entry.sha256));
        if (rows.length !== entry.count || rows.some(row => row.month !== entry.month)) throw new Error('Invalid month coverage');
        parts[index] = rows;
        status.textContent = `正在加载月度排名：${++completed} / ${manifest.chunks.length} 个月…`;
      }
    }));
    const rows = parts.flat();
    if (rows.length !== manifest.row_count) throw new Error('Incomplete ranking data');
    window.RANKING_DATA = {...manifest.metadata, rows};
    for (const file of scripts) {
      await new Promise((resolve,reject) => {
        const script = document.createElement('script');
        script.src = file + '?v=' + encodeURIComponent(manifest.asset_version || manifest.version);
        script.onload = resolve;
        script.onerror = () => reject(new Error('Module failed to load'));
        document.body.appendChild(script);
      });
    }
  }
  start().catch(error => {
    console.error('Competitor dashboard failed to load', error);
    status.textContent = '竞品数据暂时未能加载，请刷新页面重试。';
    document.getElementById('competitor-loading').setAttribute('role','alert');
    if (embedded) parent.postMessage({type:'ph-competitor:status',error:true},location.origin);
  });
})();
