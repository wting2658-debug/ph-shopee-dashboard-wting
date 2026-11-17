(function(){
  const charts = new Map();
  let selectedProduct = null;
  let latestArgs = null;
  window.setFlashTrendProduct = product => {
    selectedProduct = product;
    if (latestArgs) window.renderFlashCharts(...latestArgs);
  };
  const numeric = value => {
    const result = Number(String(value ?? '').replace(/[,¥￥]/g, ''));
    return Number.isFinite(result) ? result : 0;
  };
  const normalizedDate = value => {
    const match = String(value ?? '').match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    return match ? `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}` : '';
  };
  const dates = (start, end) => {
    const result = [];
    const last = new Date(`${end}T00:00:00Z`);
    for (const cursor = new Date(`${start}T00:00:00Z`); cursor <= last; cursor.setUTCDate(cursor.getUTCDate() + 1)) {
      result.push(cursor.toISOString().slice(0, 10));
    }
    return result;
  };
  const ratio = (value, total) => total > 0 ? value / total * 100 : null;
  function draw(id, labels, datasets, rightTitle, rightSuffix) {
    if (!window.Chart) return;
    charts.get(id)?.destroy();
    charts.set(id, new Chart(document.getElementById(id), {
      type: 'bar',
      data: {labels, datasets},
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {legend: {position: 'top', labels: {usePointStyle: true}}},
        scales: {
          x: {grid: {display: false}, ticks: {maxRotation: 45, autoSkip: labels.length > 16}},
          y: {beginAtZero: true, title: {display: true, text: 'GMV（¥）'}, ticks: {callback: value => Number(value).toLocaleString('zh-CN')}},
          right: {type: 'linear', position: 'right', beginAtZero: true, title: {display: true, text: rightTitle},
            grid: {drawOnChartArea: false}, ticks: {callback: value => `${value}${rightSuffix}`}}
        }
      }
    }));
  }
  window.renderFlashCharts = function(data, source, range) {
    if (!source?.category_gmv) return;
    latestArgs = [data, source, range];
    const periods = [[range.start, range.end], [range.previousStart, range.previousEnd]];
    const categoryTotals = new Map();
    for (const [day, category, amount] of source.category_gmv) {
      const totals = categoryTotals.get(category) || [0, 0, 0, 0];
      periods.forEach(([start, end], index) => {
        if (day >= start && day <= end) totals[index * 2 + 1] += amount;
      });
      categoryTotals.set(category, totals);
    }
    source.detail.slice(1).forEach(row => {
      const day = normalizedDate(row[0]), category = row[8]?.trim();
      if (!category) return;
      const totals = categoryTotals.get(category) || [0, 0, 0, 0];
      periods.forEach(([start, end], index) => {
        if (day >= start && day <= end) totals[index * 2] += numeric(row[12]);
      });
      categoryTotals.set(category, totals);
    });
    const categories = [...categoryTotals.entries()].filter(([, totals]) => totals[0] || totals[2])
      .sort((left, right) => right[1][0] - left[1][0]);
    const pick = index => categories.map(([, totals]) => totals[index]);
    draw('flash-category-chart', categories.map(([category]) => category), [
      {label: '当期闪购 GMV', data: pick(0), backgroundColor: '#569b8b', borderColor: '#569b8b', yAxisID: 'y'},
      {label: '对比闪购 GMV', data: pick(2), backgroundColor: '#bedcd4', borderColor: '#74aa9e', yAxisID: 'y'},
      {type: 'line', label: '当期占比', data: categories.map(([, totals]) => ratio(totals[0], totals[1])), borderColor: '#e96636', backgroundColor: '#e96636', yAxisID: 'right', tension: .2},
      {type: 'line', label: '对比占比', data: categories.map(([, totals]) => ratio(totals[2], totals[3])), borderColor: '#f0b5a1', backgroundColor: '#f0b5a1', borderDash: [5, 4], yAxisID: 'right', tension: .2}
    ], '闪购占品类 GMV', '%');
    const currentDates = dates(range.start, range.end);
    const previousDates = dates(range.previousStart, range.previousEnd);
    const gmv = new Map();
    const pits = new Map();
    if (selectedProduct) {
      const productPits = new Map();
      for (const row of source.detail.slice(1)) {
        if (row[9]?.trim() !== selectedProduct) continue;
        const day = normalizedDate(row[0]);
        if (!day) continue;
        gmv.set(day, (gmv.get(day) || 0) + numeric(row[12]));
        if (!productPits.has(day)) productPits.set(day, numeric(row[11]));
      }
      for (const [day, value] of productPits) pits.set(day, value);
    } else {
      for (const row of data.daily) gmv.set(row.date, row.gmv);
      for (const row of data.detail) if (!pits.has(row.date)) pits.set(row.date, row.pit);
    }
    document.getElementById('flash-trend-selection').textContent = selectedProduct
      ? `当前产品：${selectedProduct} · 再次点击该产品可返回全店`
      : '当前显示：全店闪购数据';
    const length = Math.max(currentDates.length, previousDates.length);
    const at = (period, values) => Array.from({length}, (_, index) => period[index] ? values.get(period[index]) ?? null : null);
    draw('flash-daily-chart', Array.from({length}, (_, index) => currentDates[index]?.slice(5) || previousDates[index]?.slice(5)), [
      {label: '当期 GMV', data: at(currentDates, gmv), backgroundColor: '#569b8b', yAxisID: 'y'},
      {label: '对比 GMV', data: at(previousDates, gmv), backgroundColor: '#bedcd4', yAxisID: 'y'},
      {type: 'line', label: '当期坑位', data: at(currentDates, pits), borderColor: '#e96636', backgroundColor: '#e96636', yAxisID: 'right', tension: .2},
      {type: 'line', label: '对比坑位', data: at(previousDates, pits), borderColor: '#f0b5a1', backgroundColor: '#f0b5a1', borderDash: [5, 4], yAxisID: 'right', tension: .2}
    ], '坑位数', '');
  };
})();

