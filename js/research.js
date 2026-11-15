/* Independent, data-driven renderer for the public research page. */
(() => {
  const STRINGS = {
    ru: { skip:'К результатам', title:'результаты исследования', dashboard:'← Обзор', finding:'Находка', matching:'Сопоставление радаров', ablation:'Устойчивость и абляции', heading:'Что выдерживает проверку: сопоставление радаров и устойчивость аномалий', intro:'Исследование проверяет согласованность наблюдений NISAR L-band и Sentinel-1 C-band и устойчивость пространственных кандидатов к выбору дат, порогов и масштаба.', loading:'Загрузка результатов…', missing:'Результаты исследования пока готовятся. На этой странице появятся проверенные выводы, matching, абляции, источники и инструкции воспроизведения.', error:'Не удалось загрузить результаты. Попробуйте обновить страницу позже.', evidence:'Сила и ограничения доказательств', sources:'Источники', repro:'Воспроизводимость', back:'Вернуться к dashboard', noData:'Для этого раздела пока нет опубликованных результатов.', strength:'Что поддерживает вывод', limitations:'Ограничения интерпретации', summary:'Кратко', table:'Числа для проверки', chart:'График', x:'Наблюдение', y:'Значение', source:'Источник', command:'Команда', openAmazon:'Открыть участок Амазонии в dashboard', design:'Два разных дизайна выборки — не объединять' },
    en: { skip:'Skip to results', title:'research results', dashboard:'← Dashboard', finding:'Finding', matching:'Radar matching', ablation:'Robustness and ablations', heading:'What withstands scrutiny: radar matching and anomaly robustness', intro:'This study tests agreement between NISAR L-band and Sentinel-1 C-band observations, and the stability of spatial candidates under different dates, thresholds and scales.', loading:'Loading results…', missing:'Research results are being prepared. Verified findings, matching, ablations, sources and reproduction instructions will appear here.', error:'Could not load the results. Please try again later.', evidence:'Evidence strength and limitations', sources:'Sources', repro:'Reproducibility', back:'Back to dashboard', noData:'No results have been published for this section yet.', strength:'What supports the finding', limitations:'Limits on interpretation', summary:'In brief', table:'Values for inspection', chart:'Chart', x:'Observation', y:'Value', source:'Source', command:'Command', openAmazon:'Open Amazon in the dashboard', design:'Two distinct sample designs — do not combine' }
  };
  const COLORS = ['#000080','#c00000','#007a1f','#d86b00','#0050c8','#67217a'];
  const $ = id => document.getElementById(id);
  let language = 'ru';
  let statusKey = 'loading';
  const chartRecords = new Map();
  const chartObservers = new Map();
  const text = key => STRINGS[language][key] || key;
  const locale = () => language === 'ru' ? 'ru-RU' : 'en-US';
  function formatNumber(value, signed=false, digits=3) {
    const n=Number(value); if(!Number.isFinite(n)) return String(value ?? '');
    return new Intl.NumberFormat(locale(),{maximumFractionDigits:digits,signDisplay:signed?'always':'auto'}).format(n);
  }
  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined && content !== null) node.textContent = String(content);
    return node;
  }
  function localized(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) return value[language] ?? value.en ?? value.ru ?? '';
    return value == null ? '' : value;
  }
  function paragraph(parent, value) {
    const resolved = localized(value);
    if (resolved !== '') parent.appendChild(element('p', '', resolved));
  }
  function list(parent, items) {
    if (!Array.isArray(items) || !items.length) return;
    const ul = element('ul', 'research-list');
    items.forEach(item => ul.appendChild(element('li', '', localized(item))));
    parent.appendChild(ul);
  }
  function sectionContent(parent, value) {
    if (value == null || value === '') { parent.appendChild(element('p', '', text('noData'))); return; }
    if (typeof value === 'string' || (typeof value === 'object' && !Array.isArray(value) && ('ru' in value || 'en' in value))) { paragraph(parent, value); return; }
    if (Array.isArray(value)) { list(parent, value); return; }
    if (typeof value !== 'object') { paragraph(parent, value); return; }
    paragraph(parent, value.summary ?? value.text ?? value.description);
    if (value.strength != null) { parent.appendChild(element('h3','research-section-title',text('strength'))); paragraph(parent,value.strength); }
    if (value.limitations != null) { parent.appendChild(element('h3','research-section-title',text('limitations'))); listOrParagraph(parent,value.limitations); }
    list(parent, value.points ?? value.items);
    if (value.table) renderTable(parent, value.table);
    if (Array.isArray(value.tables)) value.tables.forEach(item=>renderTableBlock(parent,item));
    if (Array.isArray(value.charts)) value.charts.forEach(chart => renderChart(parent, chart));
    if (value.chart) renderChart(parent, value.chart);
    if (value.sources) listOrParagraph(parent, value.sources);
    if (value.commands) renderCommands(parent, value.commands);
    if (Array.isArray(value.details)) value.details.forEach(detail=>renderDetail(parent,detail));
    if (!Object.keys(value).some(k => ['summary','text','description','strength','limitations','points','items','table','tables','charts','chart','sources','commands','details'].includes(k))) paragraph(parent, localized(value));
  }
  function listOrParagraph(parent, value) { Array.isArray(value) ? list(parent,value) : paragraph(parent,value); }
  function renderTable(parent, table) {
    if (!table || !Array.isArray(table.rows) || !table.rows.length) return;
    const columns = Array.isArray(table.columns) ? table.columns : Object.keys(table.rows[0]);
    if (!columns.length) return;
    const wrap = element('div','research-table-wrap');
    const tbl = element('table','research-table'); tbl.setAttribute('role','table');
    const head = document.createElement('thead'), tr = document.createElement('tr');
    columns.forEach(col => tr.appendChild(element('th','',localized(typeof col === 'object' ? col.label : col))));
    head.appendChild(tr); tbl.appendChild(head);
    const body = document.createElement('tbody');
    table.rows.forEach(row => { const line = document.createElement('tr'); columns.forEach((col,i) => {
      const key = typeof col === 'object' ? col.key : col;
      const value = Array.isArray(row) ? row[i] : row?.[key];
      const columnSpec=typeof columns[i]==='object'?columns[i]:{};
      line.appendChild(element('td','',typeof value==='number'?formatNumber(value,!!columnSpec.signed,columnSpec.digits??3):localized(value)));
    }); body.appendChild(line); });
    tbl.appendChild(body); wrap.appendChild(tbl); parent.appendChild(wrap);
  }
  function renderTableBlock(parent, block) {
    if (block?.title) parent.appendChild(element('h3','research-section-title',localized(block.title)));
    renderTable(parent,block?.table ?? block);
    paragraph(parent,block?.note);
  }
  function renderDetail(parent, detail) {
    if(!detail || typeof detail!=='object') return;
    const disclosure=document.createElement('details'); disclosure.className='research-details';
    disclosure.appendChild(element('summary','',localized(detail.title)));
    const content=element('div','research-details__body');
    if(detail.text) paragraph(content,detail.text);
    if(detail.items) listOrParagraph(content,detail.items);
    if(detail.table) renderTableBlock(content,{title:detail.table_title,table:detail.table});
    if(detail.tables) detail.tables.forEach(item=>renderTableBlock(content,item));
    if(detail.links) renderSources(content,detail.links);
    disclosure.appendChild(content); parent.appendChild(disclosure);
  }
  function renderCards(cards) {
    const parent=$('research-cards'); parent.replaceChildren();
    (cards||[]).forEach(card=>{
      const article=element('article','research-card'); article.appendChild(element('h3','',localized(card.label)));
      const values=element('div','research-card__values');
      (card.values||[]).forEach(item=>{
        const row=element('div','research-card__value');
        if(item.label) row.appendChild(element('span','research-card__label',localized(item.label)));
        const shown=element('strong','',formatNumber(item.value,card.signed!==false));
        if(card.unit) shown.appendChild(document.createTextNode(` ${localized(card.unit)}`));
        row.appendChild(shown); values.appendChild(row);
      });
      article.appendChild(values); paragraph(article,card.note); parent.appendChild(article);
    });
  }
  function renderCommands(parent, commands) {
    const items = Array.isArray(commands) ? commands : [commands];
    items.forEach(item => {
      const row = element('p');
      if (item && typeof item === 'object') { if (item.label) row.appendChild(element('strong','',localized(item.label) + ': ')); row.appendChild(element('code','',localized(item.command ?? item.text))); }
      else row.appendChild(element('code','',localized(item)));
      parent.appendChild(row);
    });
  }
  function safeLocalHref(href) {
    if (typeof href !== 'string' || !href.trim() || href.startsWith('/') || href.startsWith('\\') || href.includes('\\') || /^[a-z][a-z\d+.-]*:/i.test(href)) return null;
    if (href.split(/[?#]/, 1)[0].split('/').some(part => part === '..')) return null;
    try {
      const resolved = new URL(href, window.location.href);
      return resolved.origin === window.location.origin ? resolved.href : null;
    } catch (_) { return null; }
  }
  function renderSources(parent, sources) {
    if (sources == null || sources === '') { parent.appendChild(element('p','',text('noData'))); return; }
    const items = Array.isArray(sources) ? sources : (sources && Array.isArray(sources.items) ? sources.items : [sources]);
    const ul = element('ul','research-list');
    items.forEach(source => {
      const li = document.createElement('li');
      if (source && typeof source === 'object' && !Array.isArray(source)) {
        const label = localized(source.label ?? source.title ?? source.href);
        const href = safeLocalHref(source.href);
        if (href) {
          const link = element('a','',label); link.setAttribute('href',href);
          if (source.download) link.setAttribute('download',typeof source.download === 'string' ? source.download : '');
          li.appendChild(link);
        } else li.textContent = String(label ?? '');
      } else li.textContent = String(localized(source));
      ul.appendChild(li);
    });
    if (items.length) parent.appendChild(ul);
  }
  function clearCharts(parent) {
    parent.querySelectorAll?.('canvas.research-chart').forEach(canvas => {
      chartObservers.get(canvas)?.disconnect(); chartObservers.delete(canvas); chartRecords.delete(canvas);
    });
  }
  function renderChart(parent, chart) {
    if (!chart || !Array.isArray(chart.series) || !chart.series.length) return;
    const title = localized(chart.title); if (title) parent.appendChild(element('h3','research-section-title',title));
    const canvas = element('canvas','research-chart'); canvas.setAttribute('role','img'); canvas.setAttribute('aria-label',String(title || text('chart'))); canvas.style.height='220px'; parent.appendChild(canvas);
    const legend = element('div','research-legend');
    chart.series.forEach((series,i) => { const item=element('span','',localized(series.label || `${text('y')} ${i+1}`)); item.style.setProperty('--series-color',COLORS[i%COLORS.length]); legend.appendChild(item); });
    parent.appendChild(legend);
    chartRecords.set(canvas, chart);
    drawChart(canvas, chart);
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => drawChart(canvas, chart)); observer.observe(canvas); chartObservers.set(canvas, observer);
    }
  }
  function drawChart(canvas, chart) {
    const ctx=canvas.getContext && canvas.getContext('2d'); if (!ctx) return;
    const bounds=canvas.getBoundingClientRect?.();
    const w=Math.max(1,bounds?.width || canvas.clientWidth || 600), h=Math.max(1,bounds?.height || 220), ratio=window.devicePixelRatio, dpr=Number.isFinite(ratio)&&ratio>0?ratio:1;
    const pixelWidth=Math.round(w*dpr), pixelHeight=Math.round(h*dpr);
    if(canvas.width!==pixelWidth) canvas.width=pixelWidth;
    if(canvas.height!==pixelHeight) canvas.height=pixelHeight;
    ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h); ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);
    const series=chart.series.map(s=>({...s,values:Array.isArray(s.values)?s.values:[]}));
    const numeric = point => {
      const raw=point !== null && typeof point==='object' ? point.value : point;
      if(raw===null || raw===undefined || (typeof raw==='string' && raw.trim()==='')) return NaN;
      if(typeof raw!=='number' && typeof raw!=='string') return NaN;
      const value=Number(raw);
      return Number.isFinite(value)?value:NaN;
    };
    const nums=series.flatMap(s=>s.values.map(numeric).filter(Number.isFinite));
    if (!nums.length) return;
    let min=Math.min(0,...nums),max=Math.max(0,...nums); if(min===max){min-=1;max+=1;}
    const pad={l:42,r:12,t:12,b:34}, plotW=w-pad.l-pad.r, plotH=h-pad.t-pad.b;
    ctx.font='12px Tahoma,sans-serif';ctx.fillStyle='#333';ctx.strokeStyle='#ddd';ctx.lineWidth=1;
    if(chart.type==='bar') {
      const categories=chart.labels||[];
      for(let j=0;j<=4;j++){const v=min+(max-min)*j/4,y=pad.t+plotH*(1-j/4);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.textAlign='right';ctx.fillText(formatNumber(v),pad.l-5,y+4);}
      const groupWidth=plotW/Math.max(1,categories.length), barWidth=groupWidth/(series.length+1);
      series.forEach((s,si)=>s.values.forEach((point,i)=>{const value=numeric(point);if(!Number.isFinite(value))return;
        const x=pad.l+i*groupWidth+groupWidth/2+(si-(series.length-1)/2)*barWidth-barWidth*.38;
        const y=pad.t+(max-value)/(max-min)*plotH, zero=pad.t+(max-0)/(max-min)*plotH;
        ctx.fillStyle=COLORS[si%COLORS.length];ctx.fillRect(x,Math.min(y,zero),barWidth*.76,Math.max(1,Math.abs(zero-y)));
      }));
      ctx.fillStyle='#333';ctx.textAlign='center';categories.forEach((label,i)=>ctx.fillText(String(localized(label)),pad.l+(i+.5)*groupWidth,h-8));
      return;
    }
    for(let j=0;j<=4;j++){const v=min+(max-min)*j/4,y=pad.t+plotH*(1-j/4);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.textAlign='right';ctx.fillText(Number(v.toPrecision(3)),pad.l-5,y+4);}
    series.forEach((s,si)=>{ctx.strokeStyle=COLORS[si%COLORS.length];ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=2;ctx.beginPath();let active=false;
      s.values.forEach((point,i)=>{const value=numeric(point);if(!Number.isFinite(value)){active=false;return;}const x=pad.l+(s.values.length<2?0.5:i/(s.values.length-1))*plotW,y=pad.t+(max-value)/(max-min)*plotH;if(active)ctx.lineTo(x,y);else ctx.moveTo(x,y);active=true;ctx.fillRect(x-2,y-2,4,4);
        const rawLabel=typeof point==='object' && point !== null ? point.label : (chart.labels||[])[i];const label=localized(rawLabel);if(label && (s.values.length<=8 || i===0 || i===s.values.length-1)){ctx.save();ctx.translate(x,h-7);ctx.rotate(-.35);ctx.textAlign='right';ctx.fillText(String(label),0,0);ctx.restore();}
      });ctx.stroke();
    });
  }
  function render(data) {
    const content=$('research-content');
    const sections=[['finding-content',data.finding],['evidence-content',data.evidence],['matching-content',data.matching],['ablation-content',data.ablations ?? data.ablation],['sources-content',data.sources],['repro-content',data.reproducibility ?? data.reproduction]];
    sections.forEach(([id,value])=>{const node=$(id);clearCharts(node);node.replaceChildren();if(id==='sources-content')renderSources(node,value);else sectionContent(node,value);});
    renderCards(data.cards);
    if(data.headline) $('research-heading').textContent=String(localized(data.headline));
    if(data.intro) $('research-intro-copy').textContent=String(localized(data.intro));
    if(data.dashboard_link) {
      const link=$('research-amazon-link'), href=safeLocalHref(data.dashboard_link.href);
      if(href){link.href=href;link.hidden=false;link.textContent=String(localized(data.dashboard_link.label));}
    }
    content.hidden=false;
    const summary=localized(data.summary); if(summary) $('research-status').textContent=String(summary); else $('research-status').hidden=true;
  }
  function applyLanguage() {
    document.documentElement.lang=language;
    document.querySelectorAll('[data-i18n]').forEach(node=>{const key=node.getAttribute('data-i18n');node.textContent=text(key);});
    const button=$('research-language');button.textContent=language==='ru'?'EN':'Русский';button.setAttribute('aria-label',language==='ru'?'Switch language':'Сменить язык');
    if (statusKey && !$('research-status').hidden) $('research-status').textContent=text(statusKey);
    if (!$('research-content').hidden && window.OBResearchData) render(window.OBResearchData);
  }
  $('research-language').addEventListener('click',()=>{language=language==='ru'?'en':'ru';applyLanguage();});
  applyLanguage();
  (async()=>{
    try {
      const response=await fetch('data/research/results.json');
      if (!response.ok) { if(response.status===404){statusKey='missing';$('research-status').textContent=text(statusKey);return;} throw new Error(`HTTP ${response.status}`); }
      const data=await response.json(); if(!data || typeof data!=='object' || Array.isArray(data)) throw new Error('Invalid report');
      window.OBResearchData=data; render(data);
    } catch (_) { statusKey='error';$('research-status').textContent=text(statusKey); }
  })();
  window.OBResearch = { render, renderTable, renderChart, drawChart, safeLocalHref, get language(){return language;} };
})();
