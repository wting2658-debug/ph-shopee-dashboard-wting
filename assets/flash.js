(function(){
const base='https://docs.google.com/spreadsheets/d/e/2PACX-1vQKF2KfgQeeGnMGkVIxM4viADe_msqvW-B33j_2n6_Kb7J7g5Tr5etUNjil12D4ywSflE4U7zjjnIyo/pub';
let flashData=null;
const selections={category:'',product:'',channel:''};
function parseCsv(text){const rows=[];let row=[],cell='',quoted=false;for(let index=0;index<text.length;index++){const char=text[index];if(char==='"'){if(quoted&&text[index+1]==='"'){cell+='"';index++}else quoted=!quoted}else if(char===','&&!quoted){row.push(cell);cell=''}else if((char==='\n'||char==='\r')&&!quoted){if(char==='\r'&&text[index+1]==='\n')index++;row.push(cell);if(row.some(value=>value.trim()))rows.push(row);row=[];cell=''}else cell+=char}if(cell||row.length){row.push(cell);rows.push(row)}return rows}
function number(value){const result=Number(String(value||'').replace(/[,¥￥₱]/g,''));return Number.isFinite(result)?result:0}
function date(value){const match=String(value||'').match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);return match?`${match[1]}-${match[2].padStart(2,'0')}-${match[3].padStart(2,'0')}`:''}
function sum(start,end){let shop=0,gmv=0;for(const row of flashData.daily){if(row.date>=start&&row.date<=end){shop+=row.shop;gmv+=row.gmv}}const pits=new Map();for(const row of flashData.detail){if(row.date<start||row.date>end||selections.category&&row.category!==selections.category||selections.product&&row.product!==selections.product||selections.channel&&row.channel!==selections.channel)continue;if(!pits.has(row.date))pits.set(row.date,row.pit)}const slots=[...pits.values()].reduce((total,value)=>total+value,0);return{shop,gmv,share:shop?gmv/shop:null,slots,output:slots?gmv/slots:null}}
function money(value){return value==null?'—':`¥${Math.round(value).toLocaleString('zh-CN')}`}
function renderFlashPage(){
  if(!flashData)return;
  const start=document.getElementById('start-date').value,end=document.getElementById('end-date').value;
  const compareMode=document.getElementById('flash-compare').value;
  const previousStart=compareMode==='month'?shiftMonth(start,-1):document.getElementById('compare-start-date').value;
  const previousEnd=compareMode==='month'?shiftMonth(end,-1):document.getElementById('compare-end-date').value;
  const now=sum(start,end),previous=sum(previousStart,previousEnd);
  const percent=value=>value==null?'—':`${(value*100).toFixed(2)}%`;
  const items=[['店铺 GMV · 全店基准',now.shop,previous.shop,money],['闪购 GMV',now.gmv,previous.gmv,money],['闪购占比',now.share,previous.share,percent],['闪购坑位',now.slots,previous.slots,value=>value.toLocaleString('zh-CN')],['闪购坑产',now.output,previous.output,money]];
  document.getElementById('flash-kpis').innerHTML=items.map(([label,current,prior,format])=>{
    const change=current!=null&&prior?(current-prior)/Math.abs(prior):null;
    const delta=change==null?'上期无数据':`${change>0?'+':''}${(change*100).toFixed(1)}%`;
    const color=change>0?'positive':change<0?'negative':'neutral';
    return `<article class="flash-card"><div class="flash-label">${label}</div><div class="flash-value">${format(current)}</div><div class="flash-period">${start} → ${end}<br>对比 ${previousStart} → ${previousEnd}：${format(prior)}</div><div class="flash-kpi-change ${color}">${delta}</div></article>`;
  }).join('');
  const range={start,end,previousStart,previousEnd};
  window.renderFlashCharts?.(flashData,window.FLASH_CHART_DATA,range);
  window.renderFlashProducts?.(flashData,range);
}
window.renderFlashPage=renderFlashPage;
function option(id,values,label){const select=document.getElementById(id);select.replaceChildren(new Option(label,''),...[...new Set(values.filter(Boolean))].sort().map(value=>new Option(value,value)))}
async function load(){try{const response=await fetch('assets/flash-data.json',{cache:'no-cache'});if(!response.ok)throw Error(`HTTP ${response.status}`);const source=await response.json();if(source.schema!==1)throw Error('闪购数据格式不符');window.FLASH_CHART_DATA=source;const detail=source.detail,daily=source.daily;flashData={detail:detail.slice(1).map(row=>({date:date(row[0]),pit:number(row[6]),category:row[8]?.trim(),product:row[9]?.trim(),channel:row[16]?.trim()})).filter(row=>row.date),daily:daily.slice(1).map(row=>({date:date(row[0]),shop:number(row[12]),gmv:number(row[10])})).filter(row=>row.date)};option('flash-category',flashData.detail.map(row=>row.category),'全部类目');option('flash-product',flashData.detail.map(row=>row.product),'全部商品');option('flash-channel',flashData.detail.map(row=>row.channel),'全部渠道');document.getElementById('flash-status').textContent='数据已加载';renderFlashPage()}catch(error){document.getElementById('flash-status').textContent='闪购数据加载失败：请先运行数据刷新任务生成 flash-data.json。';console.error(error)}}
document.addEventListener('click',event=>{if(event.target.closest('[data-dashboard-page="flash"]')){document.querySelectorAll('main.dashboard-page').forEach(page=>page.hidden=page.id!=='flash-page');load()}});
document.addEventListener('change',event=>{if(event.target.id.startsWith('flash-')){for(const key of Object.keys(selections))selections[key]=document.getElementById('flash-'+key).value;if(event.target.id==='flash-product')window.setFlashTrendProduct?.(selections.product||null);renderFlashPage()}else if(['start-date','end-date','compare-start-date','compare-end-date'].includes(event.target.id))renderFlashPage()});
})();

