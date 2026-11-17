(function() {
  const sort = {key: 'gmv', direction: -1};
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const amount = value => value == null ? '—' : `¥${Math.round(value).toLocaleString('zh-CN')}`;
  const date = value => {
    const match = String(value ?? '').match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    return match ? `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}` : '';
  };
  const number = value => {
    const parsed = Number(String(value ?? '').replace(/[,¥￥]/g, ''));
    return Number.isFinite(parsed) ? parsed : 0;
  };
  let lastData;
  let lastRange;
  const ratio = (numerator, denominator) => denominator > 0 ? numerator / denominator : null;
  const changeHtml = (current, previous) => {
    const change = current != null && previous ? (current - previous) / previous : null;
    return change == null
      ? '<span class="flash-change neutral">上期无数据</span>'
      : `<span class="flash-change ${change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral'}">${change > 0 ? '+' : ''}${(change * 100).toFixed(1)}%</span>`;
  };
  const cell = (current, previous, formatter) =>
    `<td><strong>${formatter(current)}</strong><br>${changeHtml(current, previous)}</td>`;

  function render(data, range) {
    lastData = data;
    lastRange = range;
    const products = new Map();
    const productGmv = new Map();
    for (const [day, product, sales] of window.FLASH_CHART_DATA?.product_gmv || []) {
      if (!productGmv.has(product)) productGmv.set(product, {current: 0, previous: 0});
      const total = productGmv.get(product);
      if (day >= range.start && day <= range.end) total.current += sales;
      if (day >= range.previousStart && day <= range.previousEnd) total.previous += sales;
    }
    for (const row of window.FLASH_CHART_DATA.detail.slice(1)) {
      const product = row[9]?.trim();
      if (!product) continue;
      const category = row[8]?.trim() || '未分类';
      const key = `${category}\u0000${product}`;
      if (!products.has(key)) products.set(key, {product, category, gmv: 0, previousGmv: 0,
        slotsByDay: new Map(), previousSlotsByDay: new Map()});
      const item = products.get(key);
      const day = date(row[0]);
      if (day >= range.start && day <= range.end) {
        item.gmv += number(row[12]);
        if (!item.slotsByDay.has(day)) item.slotsByDay.set(day, number(row[11]));
      }
      if (day >= range.previousStart && day <= range.previousEnd) {
        item.previousGmv += number(row[12]);
        if (!item.previousSlotsByDay.has(day)) item.previousSlotsByDay.set(day, number(row[11]));
      }
    }
    for (const item of products.values()) {
      item.slots = [...item.slotsByDay.values()].reduce((sum, value) => sum + value, 0);
      item.previousSlots = [...item.previousSlotsByDay.values()].reduce((sum, value) => sum + value, 0);
      item.output = ratio(item.gmv, item.slots);
      item.previousOutput = ratio(item.previousGmv, item.previousSlots);
      const denominator = productGmv.get(item.product);
      item.share = ratio(item.gmv, denominator?.current);
      item.previousShare = ratio(item.previousGmv, denominator?.previous);
    }
    const rows = [...products.values()].sort((left, right) => {
      const leftValue = left[sort.key], rightValue = right[sort.key];
      if (leftValue == null || rightValue == null) {
        if (leftValue == null && rightValue != null) return 1;
        if (rightValue == null && leftValue != null) return -1;
      }
      const comparison = typeof leftValue === 'string'
        ? leftValue.localeCompare(rightValue, 'zh-CN')
        : leftValue == null ? 0 : leftValue - rightValue;
      return sort.direction * comparison || left.product.localeCompare(right.product, 'zh-CN');
    });
    document.getElementById('flash-product-rows').innerHTML = rows.map(item => {
      const percent = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
      return `<tr><td><button type="button" class="flash-product-link" data-flash-product-name="${escapeHtml(item.product)}">${escapeHtml(item.product)}</button></td><td>${escapeHtml(item.category)}</td>${cell(item.gmv, item.previousGmv, amount)}${cell(item.slots, item.previousSlots, value => value.toLocaleString('zh-CN'))}${cell(item.output, item.previousOutput, amount)}${cell(item.share, item.previousShare, percent)}</tr>`;
    }).join('') || '<tr><td colspan="6">暂无产品数据</td></tr>';
    document.querySelectorAll('[data-flash-sort]').forEach(button => {
      button.querySelector('span').textContent = button.dataset.flashSort === sort.key
        ? sort.direction === 1 ? '↑' : '↓' : '↕';
      button.setAttribute('aria-sort', button.dataset.flashSort === sort.key
        ? sort.direction === 1 ? 'ascending' : 'descending' : 'none');
    });
  }
  document.addEventListener('click', event => {
    const productButton = event.target.closest('[data-flash-product-name]');
    if (productButton) {
      const product = productButton.dataset.flashProductName;
      const active = document.querySelector('.flash-product-link.is-selected');
      const next = active?.dataset.flashProductName === product ? null : product;
      document.querySelectorAll('.flash-product-link').forEach(button => button.classList.toggle('is-selected', button.dataset.flashProductName === next));
      window.setFlashTrendProduct?.(next);
      return;
    }
    const button = event.target.closest('[data-flash-sort]');
    if (!button) return;
    const key = button.dataset.flashSort;
    sort.direction = sort.key === key ? -sort.direction : key === 'gmv' ? -1 : 1;
    sort.key = key;
    if (lastData) render(lastData, lastRange);
  });
  window.renderFlashProducts = render;
})();

