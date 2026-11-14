(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.CategoryPicker=api;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const preferred=['Skincare','Makeup','Beauty Sets & Packages','Bath & Body Care','Beauty Tools'];
  const palette=['#426df3','#20a692','#e75492','#8064dd','#de941a','#3396bf','#945ada','#bd7739','#2b8d7e','#bd527f','#548c59','#8c7b41','#b74d59','#6873c4','#508ca5','#ac6d9b','#369b91','#ad8753','#7c82ab','#609e70','#bf7556','#607bb5','#9d853e','#b664ad','#388eaf','#838a4d','#ae666b','#678eaa'];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text=(en,cn,eng)=>en?eng:cn;
  const name=(category,en=false)=>category==='Beauty'?text(en,'Beauty 总榜','Beauty overall'):category.replaceAll(' >> ',' / ');
  function catalog(tree){
    const parents=Object.keys(tree).filter(k=>!k.startsWith('_')).sort((a,b)=>(preferred.indexOf(a)<0?99:preferred.indexOf(a))-(preferred.indexOf(b)<0?99:preferred.indexOf(b))||a.localeCompare(b));
    const children=node=>Array.isArray(node)?node:Object.keys(node||{}).filter(k=>!k.startsWith('_'));
    const sections=[{key:'root',categories:['Beauty']},{key:'level2',categories:parents.map(p=>'Beauty >> '+p)},...parents.filter(p=>children(tree[p]).length).map(p=>({key:p,level:3,categories:children(tree[p]).map(child=>'Beauty >> '+p+' >> '+child)}))];
    for(const parent of parents){
      const node=tree[parent];if(Array.isArray(node))continue;
      for(const child of children(node)){
        const leaves=children(node[child]);
        if(leaves.length)sections.push({key:parent+' / '+child,level:4,categories:leaves.map(leaf=>'Beauty >> '+parent+' >> '+child+' >> '+leaf)});
      }
    }
    const categories=sections.flatMap(s=>s.categories),colors=Object.fromEntries(categories.map((c,i)=>[c,palette[i%palette.length]]));
    return {sections,categories,colors};
  }
  function sectionTitle(section,en){return section.key==='root'?'':section.key==='level2'?text(en,'二级类目','Level 2 categories'):section.key+text(en,section.level===4?' · 四级类目':' · 三级类目',section.level===4?' · Level 4 categories':' · Level 3 categories');}
  function render({id,label,tree,selected,multiple=false,en=false,allowAll=false,open=false,extraClass=''}){
    const chosen=new Set(multiple?selected:[selected]),count=tree.categories.filter(c=>chosen.has(c)).length;
    const summary=multiple?text(en,`已选 ${count} / ${tree.categories.length} 个榜单`,`Selected ${count} / ${tree.categories.length} rankings`):selected?name(selected,en):text(en,'全部榜单','All rankings');
    const option=(value,all=false)=>`<label class="ranking-choice ${value.split(' >> ').length>=3?'ranking-choice-child':''} ${chosen.has(value)?'is-selected':''}" title="${esc(all?text(en,'全部榜单','All rankings'):name(value,en))}"><input type="${multiple?'checkbox':'radio'}" name="${esc(id)}-choice" value="${esc(value)}" ${chosen.has(value)?'checked':''}><i class="ranking-category-dot" style="background:${all?'#94a7b7':tree.colors[value]}" aria-hidden="true"></i><span>${esc(all?text(en,'全部榜单','All rankings'):name(value,en))}</span></label>`;
    return `<div class="ranking-picker-field ${extraClass}"><span class="filter-label" id="${esc(id)}-label">${esc(label)}</span><details class="ranking-picker" id="${esc(id)}" ${open?'open':''}><summary aria-labelledby="${esc(id)}-label ${esc(id)}-value"><span id="${esc(id)}-value">${!multiple?`<i class="ranking-category-dot" style="background:${selected?tree.colors[selected]:'#94a7b7'}" aria-hidden="true"></i>`:''}${esc(summary)}</span><span class="ranking-picker-chevron" aria-hidden="true">⌄</span></summary><div class="ranking-menu"><div class="ranking-picker-actions"><button type="button" data-category-action="default">${text(en,'恢复默认','Restore defaults')}</button>${multiple?`<button type="button" data-category-action="all">${text(en,'全选','Select all')}</button><button type="button" data-category-action="none">${text(en,'清空','Clear')}</button>`:allowAll?`<button type="button" data-category-action="none">${text(en,'全部榜单','All rankings')}</button>`:''}<button type="button" data-category-action="done">${text(en,'完成','Done')}</button></div><div class="ranking-category-options" role="group" aria-labelledby="${esc(id)}-label">${allowAll?option('',true):''}${tree.sections.map(section=>`<div class="ranking-category-section">${sectionTitle(section,en)?`<div class="ranking-category-group">${esc(sectionTitle(section,en))}</div>`:''}${section.categories.map(c=>option(c)).join('')}</div>`).join('')}</div></div></details></div>`;
  }
  function size(picker){
    if(!picker?.open)return;
    const viewportWidth=document.documentElement.clientWidth,viewportHeight=document.documentElement.clientHeight;
    const menu=picker.querySelector('.ranking-menu'),rect=picker.querySelector('summary').getBoundingClientRect(),width=Math.min(viewportWidth-24,Math.max(rect.width,Math.min(660,viewportWidth-24)));
    const below=viewportHeight-rect.bottom-16,above=rect.top-16,up=below<240&&above>below,available=Math.max(100,up?above:below);
    menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(rect.left,viewportWidth-width-12))+'px';menu.style.maxHeight=Math.min(600,available)+'px';
    menu.style.top=up?'auto':rect.bottom+8+'px';menu.style.bottom=up?viewportHeight-rect.top+8+'px':'auto';
  }
  function closeAll(except){document.querySelectorAll('.ranking-picker[open]').forEach(p=>{if(p!==except)p.open=false;});}
  function bind(id,{tree,multiple=false,defaults,onChange,onOpen=()=>{}}){
    const picker=document.getElementById(id);if(!picker)return;
    const close=focus=>{picker.open=false;onOpen(false);if(focus)picker.querySelector('summary').focus({preventScroll:true});};
    picker.ontoggle=()=>{if(!picker.isConnected)return;onOpen(picker.open);if(picker.open){document.querySelectorAll('.self-picker[open],#history-shop-picker[open]').forEach(other=>{other.open=false;});closeAll(picker);size(picker);}};
    picker.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close(true);}else if(e.target.tagName==='SUMMARY'&&['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();picker.open=true;onOpen(true);closeAll(picker);size(picker);const inputs=[...picker.querySelectorAll('.ranking-choice input')],target=inputs.find(i=>i.checked)||(e.key==='ArrowDown'?inputs[0]:inputs.at(-1));target?.focus({preventScroll:true});target?.closest('label').scrollIntoView({block:'nearest'});}};
    const update=(value,focusValue)=>{
      const scroll=picker.querySelector('.ranking-category-options').scrollTop;
      onOpen(multiple);if(!multiple)picker.open=false;
      onChange(value);
      const next=document.getElementById(id);if(!next)return;
      if(multiple){next.open=true;size(next);next.querySelector('.ranking-category-options').scrollTop=scroll;const input=[...next.querySelectorAll('.ranking-choice input')].find(i=>i.value===focusValue);(input||next.querySelector('summary')).focus({preventScroll:true});}
      else next.querySelector('summary').focus({preventScroll:true});
    };
    picker.querySelectorAll('.ranking-choice input').forEach(input=>input.onchange=()=>update(multiple?new Set([...picker.querySelectorAll('.ranking-choice input:checked')].map(i=>i.value)):input.value,input.value));
    picker.querySelectorAll('[data-category-action]').forEach(button=>button.onclick=()=>{
      const action=button.dataset.categoryAction;if(action==='done'){close(true);return;}
      const value=action==='default'?(typeof defaults==='function'?defaults():defaults):action==='all'?tree.categories:multiple?[]:'';
      update(multiple?new Set(value):value);
    });
    if(picker.open)size(picker);
  }
  if(typeof document!=='undefined'){
    document.addEventListener('click',e=>{if(!e.target.closest('.ranking-picker'))closeAll();});
    const resize=()=>document.querySelectorAll('.ranking-picker[open]').forEach(size);
    window.addEventListener('resize',resize);window.addEventListener('scroll',resize,true);
  }
  return {catalog,name,render,bind,size,closeAll};
});
