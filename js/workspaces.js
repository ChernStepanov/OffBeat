// Query-addressed workspaces share one measured-data/map instance. Classic layout is reversible.
window.OB=window.OB||{};
OB.pages=(()=>{
  const $=id=>document.getElementById(id),valid=['home','map','stories','review','data'];
  const titles={home:'Home',map:'Map workspace',stories:'Change stories',review:'Review queue',data:'Data and methods'};
  const initial=new URL(location.href),key='offbeat.layout.v1';let classic=initial.searchParams.get('layout')==='classic';
  if(!initial.searchParams.has('layout'))try{classic=localStorage.getItem(key)==='classic';}catch{}
  function inferred(url){const p=url.searchParams.get('page');if(valid.includes(p))return p;if(url.hash.includes('review'))return 'review';if(url.searchParams.has('case')||url.hash.startsWith('#tour'))return 'stories';if(url.searchParams.has('site')||url.searchParams.has('sample')||url.searchParams.has('lat')||url.hash.includes('map'))return 'map';return 'home';}
  let page=inferred(initial),changing=false;
  const nav=document.createElement('nav');nav.id='workspace-nav';nav.setAttribute('aria-label','Workspace navigation');
  for(const id of valid){const a=document.createElement('a');a.className='btn';a.dataset.page=id;a.href='?page='+id;a.textContent=titles[id];nav.append(a);}
  const controls=document.createElement('button');controls.type='button';controls.className='btn workspace-controls';controls.textContent='Map layers and threshold';controls.setAttribute('aria-expanded','false');controls.addEventListener('click',()=>{const open=document.body.classList.toggle('workspace-controls-open');controls.setAttribute('aria-expanded',String(open));OB.app?.resizeMaps();});nav.append(controls);
  const toggle=document.createElement('button');toggle.type='button';toggle.className='btn';toggle.id='layout-toggle';nav.append(toggle);document.querySelector('.app-bar').append(nav);
  const peek=document.createElement('button');peek.type='button';peek.className='btn workspace-chat-peek';peek.textContent='+';peek.setAttribute('aria-label','OffBeat Copilot');peek.setAttribute('aria-expanded','false');peek.addEventListener('click',()=>{const open=$('copilot-win').classList.toggle('copilot--peek');peek.setAttribute('aria-expanded',String(open));});$('copilot-win').querySelector('.win-t').append(peek);
  const home=document.createElement('section');home.className='workspace-start';home.id='workspace-start';
  for(const [target,text]of [['map','Find a place'],['stories','Investigate a change'],['review','Open review queue']]){const a=document.createElement('a');a.href='?page='+target;a.dataset.page=target;a.className='btn';a.textContent=text;home.append(a);}
  $('copilot-win').after(home);
  const dataLinks=document.createElement('section');dataLinks.className='win workspace-data-links';const links=document.createElement('div');links.className='win-b';for(const[href,title]of [['research.html','Calculation, figures and sources'],['candidates.html','Check the evidence'],['docs/real-nisar.md','Processing and limitations']]){const a=document.createElement('a');a.href=href;a.textContent=title;a.className='btn';links.append(a);}dataLinks.append(links);home.after(dataLinks);
  function owner(n){if(n.id==='copilot-win'||n.id==='workspace-start')return 'home';if(n.id==='side'||n.id==='scene-win')return 'map';if(n.classList.contains('launch'))return 'classic';
    if(n.id==='music-disclosure'||n.id==='observed-events-disclosure'||n.id==='evidence-disclosure'||n.id==='tour-win'||n.id==='detected-panel'||n.querySelector('#suggestions-list'))return 'stories';
    if(n.id==='review-disclosure')return 'review';
    if(['map-win','card-win','ranking-controls','val-win'].includes(n.id)||n.querySelector('#top-win'))return 'map';return 'data';}
  const roots=[...$('main').children,$('side'),document.querySelector('.launch'),$('music-disclosure'),$('observed-events-disclosure'),$('scene-win')].filter(Boolean);
  for(const n of roots)n.dataset.workspace=owner(n);
  function apply(){changing=true;document.title='OffBeat / '+(OB.i18n?.t(classic?'Classic overview':titles[page])||titles[page]);document.body.classList.toggle('workspaces-active',!classic);document.body.dataset.workspace=page;
    for(const n of roots){const chat=n.id==='copilot-win'&&(n.classList.contains('copilot--float')||n.classList.contains('copilot--full'));n.classList.toggle('workspace-hidden',!classic&&n.dataset.workspace!==page&&!chat);}
    nav.querySelectorAll('[data-page]').forEach(a=>{if(!classic&&a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    toggle.textContent=classic?'Use workspaces':'Classic overview';toggle.setAttribute('aria-pressed',String(classic));
    requestAnimationFrame(()=>{OB.app?.resizeMaps();window.dispatchEvent(new Event('resize'));changing=false;});}
  async function go(next,{replace=false}={}){if(!valid.includes(next))return;await OB.windows?.restore();if($('map-max')?.getAttribute('aria-pressed')==='true')$('map-max').click();
    const chat=$('copilot-win');if(next!=='home'&&page==='home')chat.classList.add('copilot--float');if(next==='home'){chat.classList.remove('copilot--float','copilot--full');}
    page=next;const url=new URL(location.href);url.searchParams.set('page',page);url.hash='';history[replace?'replaceState':'pushState'](null,'',url);apply();window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
  function openFor(node){if(classic||!node)return;const root=roots.find(r=>r===node||r.contains(node));if(root&&valid.includes(root.dataset.workspace)&&root.dataset.workspace!==page){if(page==='home'&&root.dataset.workspace!=='home')$('copilot-win').classList.add('copilot--float');page=root.dataset.workspace;const url=new URL(location.href);url.searchParams.set('page',page);history.pushState(null,'',url);apply();}if(root?.tagName==='DETAILS')root.open=true;}
  nav.addEventListener('click',e=>{const a=e.target.closest('[data-page]');if(a){e.preventDefault();go(a.dataset.page);}});
  home.addEventListener('click',e=>{const a=e.target.closest('[data-page]');if(a){e.preventDefault();go(a.dataset.page);}});
  toggle.addEventListener('click',()=>{classic=!classic;try{localStorage.setItem(key,classic?'classic':'workspaces');}catch{}const url=new URL(location.href);url.searchParams.set('layout',classic?'classic':'workspaces');history.replaceState(null,'',url);apply();});
  document.addEventListener('click',e=>{const link=e.target.closest('a[href^="#"]');if(link){const id=link.getAttribute('href').slice(1);openFor($(id)||id.startsWith('tour/')&&$('tour-win'));}},true);
  window.addEventListener('popstate',()=>{const url=new URL(location.href);page=inferred(url);classic=url.searchParams.get('layout')==='classic';apply();});
  document.addEventListener('ob:ready',apply,{once:true});document.addEventListener('ob:language-change',apply);OB.i18n?.ready.then(apply);
  new MutationObserver(()=>{if(!changing)apply();}).observe($('copilot-win'),{attributes:true,attributeFilter:['class']});
  apply();return {go,openFor,get page(){return page;},get classic(){return classic;}};
})();
