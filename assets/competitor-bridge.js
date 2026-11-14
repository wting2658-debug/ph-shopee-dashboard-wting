/* This classic script runs after the unchanged ranking modules. */
dashboardReady = true;
render();
document.body.removeAttribute('data-loading');
document.getElementById('competitor-loading').remove();
if (new URLSearchParams(location.search).get('embedded') === '1') {
  let competitorLastHeight = 0;
  const notifyCompetitorParent = () => {
    const height = Math.max(300, Math.ceil(document.querySelector('main').getBoundingClientRect().height));
    if (height === competitorLastHeight) return;
    competitorLastHeight = height;
    parent.postMessage({
      type:'ph-competitor:status', height,
      start:data.coverage.start, end:data.coverage.end, updated:data.updated_at,
    }, location.origin);
  };
  new ResizeObserver(notifyCompetitorParent).observe(document.querySelector('main'));
  notifyCompetitorParent();
}
