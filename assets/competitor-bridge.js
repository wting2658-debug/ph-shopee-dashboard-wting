/* This classic script runs after the unchanged ranking modules. */
dashboardReady = true;
render();
document.body.removeAttribute('data-loading');
document.getElementById('competitor-loading').remove();
if (new URLSearchParams(location.search).get('embedded') === '1') {
  const scrollArea = document.querySelector('.competitor-scroll');
  const controls = document.querySelector('.controls');
  controls.addEventListener('click', event => {
    if (event.target.closest('[data-tab]')) scrollArea.scrollTop = 0;
  });
  controls.addEventListener('change', () => { scrollArea.scrollTop = 0; });
  parent.postMessage({
    type:'ph-competitor:status',
    start:data.coverage.start, end:data.coverage.end, updated:data.updated_at,
  }, location.origin);
}
