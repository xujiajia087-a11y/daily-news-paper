/* ============================================================
   JiaJia Daily 5.0 — App Logic
   现代情报日报交互引擎
   ============================================================ */
(function(){
'use strict';
let DATA=null, WATCHLIST=[];
let fState={search:'',cat:'all',sort:'importance',chip:null};
const AC=['anime_collab','merch_release','manga_signing_events','seiyuu_events','japan_event_calendar'];
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
const esc=v=>{const d=document.createElement('div');d.textContent=v||'';return d.innerHTML};

function clsCat(item){
  const c=item.category||'';
  if(AC.includes(c))return'a';if(c==='ai_tech')return't';if(c==='politics_world')return'p';
  if((item.us_market_relevance||'')==='high'||(item.us_market_relevance||'')==='very_high')return'm';return'';
}
function caCls(item){const c=clsCat(item);return c==='a'?'an':c==='m'?'mk':c==='p'?'pl':'';}

// ---- DATA LOADING ----
async function loadData(){
  try{
    const[r1,r2]=await Promise.all([fetch('data/daily-news.json'),fetch('data/watchlist.json')]);
    if(!r1.ok)throw new Error('JSON HTTP '+r1.status);
    if(!r2.ok)throw new Error('WL HTTP '+r2.status);
    DATA=await r1.json(); WATCHLIST=await r2.json(); return true;
  }catch(e){window._loadError=e.message;console.error(e);return false}
}

// ---- HERO ----
function renderHero(){
  const m=DATA.metadata||{}, ov=DATA.daily_overview||{};
  const stats=[
    ['📥 抓取',m.total_fetched],['✅ 入选',m.selected_count],
    ['🎌 动漫',m.anime_event_count],['📈 美股',m.market_related_count],
    ['🔭 追踪',m.watchlist_count]
  ];
  $('#hero-area').innerHTML=`
    <div class="date-big">${esc(m.report_date||'')} ${esc(m.report_weekday||'')}<em>JiaJia Daily · Intelligence Edition</em></div>
    <div class="sub-info">🕐 ${esc(m.generated_at||'')} · ${esc(m.timezone||'')} · 数据窗口: ${esc(m.data_window||'')}</div>
    <div class="stat-strip">${stats.map(([l,v])=>{
      let cls='';if(l.includes('动漫'))cls='anime';else if(l.includes('美股'))cls='market';
      return `<span class="stat-chip ${cls}">${l} <b>${v||0}</b></span>`;
    }).join('')}</div>
    <div class="overview-line">📋 ${esc(ov.one_sentence_cn||'')}<br><em>市场情绪: ${esc(ov.market_mood_cn||'')} | 动漫情报: ${esc(ov.anime_event_mood_cn||'')}</em></div>`;
}

// ---- QUICK BRIEF (30秒) ----
function renderBrief(){
  const eb=DATA.executive_brief||{};
  const secs=[
    ['📌 今日核心判断',eb.top_5_judgements,'gold'],
    ['🎌 动漫/周边值得蹲',eb.anime_merch_signing_highlights,'anime'],
    ['🤖 AI科技重点',eb.ai_tech_highlights,'tech'],
    ['📈 美股影响',eb.us_stock_market_impacts,'market'],
    ['🔇 可忽略的噪音',eb.noise_or_low_priority,''],
  ].filter(s=>s[1]&&s[1].length);
  $('#brief-container').innerHTML='<div class="brief-grid">'+secs.map(([t,items,cls])=>`
    <div class="b-card ${cls}"><h4>${t}</h4><ul>${items.slice(0,5).map(i=>`<li>${esc(i)}</li>`).join('')}</ul></div>
  `).join('')+'</div>';
  if(eb.final_editor_note){
    $('#brief-container').innerHTML+=`<p class="brief-note">✒️ ${esc(eb.final_editor_note)}</p>`;
  }
}

// ---- IMPACT MAP ----
function renderImpact(){
  const im=DATA.impact_map||{};
  const cells=[
    ['anime_collecting','🎌','动漫收藏'],
    ['japanese_events','🗾','日本活动'],
    ['ai_tech','🤖','AI科技'],
    ['us_stocks','📈','美股'],
    ['politics_risk','🌍','政治风险'],
    ['future_watchlist','🔭','未来追踪']
  ];
  const lc={high:'#dc2626',medium:'#f59e0b',low:'#22c55e'};
  const catMap={anime_collecting:'anime',japanese_events:'anime',ai_tech:'tech',us_stocks:'market',politics_risk:'politics'};
  $('#impact-strip').innerHTML=cells.map(([k,icon,lab])=>{
    const d=im[k]||{},lv=d.level||'low';
    return `<div class="impact-dot" data-im="${k}" style="border-color:${lc[lv]}">
      <div class="id-icon">${icon}</div>
      <div class="id-level" style="color:${lc[lv]}">${lv.toUpperCase()}</div>
      <div class="id-text">${esc((d.summary_cn||lab).slice(0,50))}</div>
    </div>`;
  }).join('');
  $$('.impact-dot').forEach(d=>d.addEventListener('click',()=>{
    const m=catMap[d.dataset.im];
    if(m){fState.cat=m;$('#cat-select').value=m;}
    fState.chip=null;updateChips();renderCards();
    $('#toolbar-strip').scrollIntoView({behavior:'smooth',block:'start'});
  }));
}

// ---- TOP STORIES ----
function renderTop(){
  const items=DATA.top_stories||[];
  if(!items.length){$('#top-stories').innerHTML='<p class="empty-state">今日无头版重点</p>';return;}
  $('#top-stories').innerHTML=items.map((item,i)=>{
    const src=item.source_display_name||item.source||'?';
    const link=item.original_link||'#';
    return `<div class="top-story">
      <span class="ts-rank">No.${i+1}</span><span class="ts-meta">${esc(src)} · ${esc(item.date_display||'')}</span>
      <h3><a href="${esc(link)}" target="_blank">${esc(item.title_cn||'?')}</a></h3>
      <div class="ts-takeaway">💡 ${esc(item.key_takeaway_cn||'')}</div>
      <div class="ts-why">${esc(item.why_it_matters_cn||'')}</div>
      ${item.frontpage_reason_cn?`<div class="ts-frontpage">⭐ 入选理由: ${esc(item.frontpage_reason_cn)}</div>`:''}
    </div>`;
  }).join('');
}

// ---- SINGLE CARD (compact by default) ----
function renderCard(item){
  const cl=clsCat(item), ccl=caCls(item);
  const src=item.source_display_name||item.source||'?';
  const link=item.original_link||'#';
  const ae=item.anime_event_detail||{};
  const ia=item.impact_analysis||{};
  const nt=item.news_type||'';
  const fresh=item.is_recent?'fr':(item.is_old_context?'old':'');
  const hasAction=!!(ae.action_needed_cn||item.action_suggestion_cn);
  const fm=item.freshness_label||(item.is_recent?'今日新情报':item.is_old_context?'旧闻/背景':'');
  const frCls=item.is_recent?'fr':item.is_old_context?'old':'unk';

  // Build detail content based on news type
  let detail='';
  if(nt==='anime_event'&&ae.event_type){
    detail=`<div class="tl-grid">
      ${ae.event_type?`<span>类型</span><span>${esc(ae.event_type)}</span>`:''}
      ${ae.ip_or_work_title?`<span>作品/IP</span><span>${esc(ae.ip_or_work_title)}</span>`:''}
      ${ae.person_name?`<span>人物</span><span>${esc(ae.person_name)}</span>`:''}
      ${ae.event_date?`<span>日期</span><span>${esc(ae.event_date)} ${esc(ae.event_time||'')}</span>`:''}
      ${ae.venue?`<span>地点</span><span>${esc(ae.venue)} ${esc(ae.city||'')}</span>`:''}
      ${ae.ticket_method?`<span>票务</span><span>${esc(ae.ticket_method)} ${ae.lottery_or_first_come?'('+esc(ae.lottery_or_first_come)+')':''}</span>`:''}
      ${ae.application_period?`<span>応募期間</span><span>${esc(ae.application_period)}</span>`:''}
      ${ae.travel_feasibility?`<span>游客</span><span>${esc(ae.travel_feasibility)}</span>`:''}
    </div>`;
    if(item.short_summary_cn)detail+=`<p>${esc(item.short_summary_cn)}</p>`;
    if(ae.action_needed_cn)detail+=`<div class="action-line">🎯 ${esc(ae.action_needed_cn)}</div>`;
  }else if(nt==='tech'||nt==='politics'){
    detail=`<p>${esc(item.short_summary_cn||'')}</p>`;
    if(item.why_it_matters_cn)detail+=`<p style="font-weight:500;color:#1e293b">📌 为什么重要: ${esc(item.why_it_matters_cn)}</p>`;
    if(ia.immediate_impact_cn)detail+=`<p>⚡ 短期: ${esc(ia.immediate_impact_cn)}</p>`;
    if(ia.medium_term_impact_cn)detail+=`<p>📆 中期: ${esc(ia.medium_term_impact_cn)}</p>`;
    if(ia.long_term_impact_cn)detail+=`<p>🔭 长期: ${esc(ia.long_term_impact_cn)}</p>`;
    if(ia.affected_sectors&&ia.affected_sectors.length)detail+=`<p>🏭 板块: ${esc(ia.affected_sectors.join('、'))}</p>`;
    if(ia.us_stock_relevance)detail+=`<p>📈 美股相关性: <b>${esc(ia.us_stock_relevance)}</b></p>`;
    if(item.action_suggestion_cn)detail+=`<div class="action-line">🎯 ${esc(item.action_suggestion_cn)}</div>`;
  }else{
    if(item.short_summary_cn)detail+=`<p>${esc(item.short_summary_cn)}</p>`;
    if(item.why_it_matters_cn)detail+=`<p style="font-weight:500;color:#1e293b">📌 ${esc(item.why_it_matters_cn)}</p>`;
    if(item.action_suggestion_cn)detail+=`<div class="action-line">🎯 ${esc(item.action_suggestion_cn)}</div>`;
  }

  // Score bars
  const sv=(l,v,c)=>{
    const pct=Math.min(Math.max((v||0)*10,0),100);
    return `<i>${l}</i><b><s style="width:${pct}%;background:${c||'#3b82f6'}"></s></b>`;
  };

  // Action preview (shown even when collapsed)
  const actPrev=hasAction&&!item.is_expanded
    ?`<div class="action-preview">🎯 ${esc(ae.action_needed_cn||item.action_suggestion_cn||'')}</div>`
    :'';

  return `<div class="card ${cl} ${hasAction?'has-action':''}" data-imp="${item.importance_score||0}" data-urg="${item.urgency_score||0}" data-col="${item.collector_value||0}" data-track="${item.tracking_value||0}" data-market="${item.us_market_relevance||''}">
    <div class="card-head">
      <span class="badge ca ${ccl}">${esc(item.category||'')}</span>
      <span class="badge sr">📰 ${esc(src)}</span>
      <span style="color:var(--muted)">${esc(item.date_display||'')}</span>
      ${fm?`<span class="badge ${frCls}">${esc(fm)}</span>`:''}
    </div>
    <h3><a href="${esc(link)}" target="_blank" onclick="event.stopPropagation()">${esc(item.title_cn||'?')}</a></h3>
    <div class="kv">${sv('重要性',item.importance_score,'#dc2626')}${sv('紧急度',item.urgency_score,'#f97316')}${sv('收藏',item.collector_value,'#7c3aed')}${item.tracking_value?sv('追踪',item.tracking_value,'#0ea5e9'):''}</div>
    ${item.key_takeaway_cn?`<div class="takeaway ${cl==='a'?'an':cl==='m'?'mk':''}">💡 ${esc(item.key_takeaway_cn)}</div>`:''}
    ${actPrev}
    <div class="card-detail">${detail}</div>
    ${!item.is_expanded?'<div class="expand-hint">⋯ 点击展开完整分析</div>':''}
    <a class="src-btn" href="${esc(link)}" target="_blank" onclick="event.stopPropagation()">📎 查看原文</a>
  </div>`;
}

// ---- FILTER & SORT ----
function filterItems(){
  let items=DATA.articles||[];
  const s=fState;

  // Category filter
  if(s.cat==='anime')items=items.filter(i=>AC.includes(i.category||''));
  else if(s.cat==='market')items=items.filter(i=>{
    const r=i.us_market_relevance||'';
    return r==='high'||r==='very_high'||r==='medium';
  });
  else if(s.cat==='tech')items=items.filter(i=>i.category==='ai_tech');
  else if(s.cat==='politics')items=items.filter(i=>i.category==='politics_world');

  // Chip filter
  if(s.chip==='recent')items=items.filter(i=>i.is_recent);
  else if(s.chip==='high')items=items.filter(i=>(i.importance_score||0)>=7);
  else if(s.chip==='urgent')items=items.filter(i=>(i.urgency_score||0)>=7);
  else if(s.chip==='action')items=items.filter(i=>{
    const ae=i.anime_event_detail||{};
    return ae.action_needed_cn||i.action_suggestion_cn;
  });
  else if(s.chip==='market')items=items.filter(i=>{
    const r=i.us_market_relevance||'';
    return r==='high'||r==='very_high';
  });
  else if(s.chip==='anime')items=items.filter(i=>AC.includes(i.category||''));
  else if(s.chip==='lottery')items=items.filter(i=>{
    const ae=i.anime_event_detail||{};
    const t=ae.ticket_method||'';
    return t.includes('抽')||t.includes('lottery')||t.includes('先着');
  });

  // Search
  if(s.search){
    const q=s.search.toLowerCase();
    items=items.filter(i=>{
      const ae=i.anime_event_detail||{};
      return [i.title_cn,i.key_takeaway_cn,i.source_display_name,i.source,
        ...(i.tags||[]),ae.person_name,ae.ip_or_work_title,ae.venue].filter(Boolean).join(' ').toLowerCase().includes(q);
    });
  }

  // Sort
  const sk={importance:'importance_score',urgency:'urgency_score',tracking:'tracking_value',collector:'collector_value'}[s.sort]||'importance_score';
  items.sort((a,b)=>(b[sk]||0)-(a[sk]||0));
  return items;
}

function renderCards(){
  const items=filterItems();
  $('#result-count').textContent=`${items.length} 条`;
  $('#news-cards').innerHTML=items.length
    ?items.map(renderCard).join('')
    :'<p class="empty-state">无匹配新闻，试试调整筛选条件</p>';

  // Attach click-to-expand
  $$('#news-cards .card').forEach(c=>c.addEventListener('click',function(e){
    if(e.target.tagName==='A')return; // Don't expand when clicking links
    const wasExpanded=this.classList.contains('expanded');
    this.classList.toggle('expanded');
    if(!wasExpanded){
      this.scrollIntoView({behavior:'smooth',block:'nearest'});
    }
  }));
}

// ---- ANIME TIMELINE ----
function renderAnime(){
  let items=DATA.anime_event_highlights||[];
  if(!items.length)items=(DATA.articles||[]).filter(i=>AC.includes(i.category||''));
  if(!items.length){
    $('#anime-cards').innerHTML=`<p class="empty-state">今日未发现高价值签售/声优活动。<br>建议继续追踪 Animate、PR TIMES、LivePocket、eplus、Lawson Ticket 等来源。</p>`;
    return;
  }
  $('#anime-cards').innerHTML='<div class="anime-tl">'+items.map(item=>{
    const ae=item.anime_event_detail||{};
    const link=item.original_link||'#';
    return `<div class="tl-item">
      <div class="tl-date">${esc(ae.event_date||item.date_display||'日期未知')}<span class="tl-type">${esc(ae.event_type||'活动')}</span></div>
      <h4><a href="${esc(link)}" target="_blank">${esc(item.title_cn||'?')}</a></h4>
      <div class="tl-grid">
        ${ae.ip_or_work_title?`<span>作品/IP</span><span>${esc(ae.ip_or_work_title)}</span>`:''}
        ${ae.person_name?`<span>人物</span><span>${esc(ae.person_name)}</span>`:''}
        ${ae.event_date?`<span>活动日期</span><span>${esc(ae.event_date)} ${esc(ae.event_time||'')}</span>`:''}
        ${ae.venue?`<span>地点</span><span>${esc(ae.venue)} ${esc(ae.city||'')} ${esc(ae.country||'')}</span>`:''}
        ${ae.ticket_method?`<span>票务方式</span><span>${esc(ae.ticket_method)} ${ae.lottery_or_first_come?'('+esc(ae.lottery_or_first_come)+')':''}</span>`:''}
        ${ae.application_period?`<span>応募期間</span><span>${esc(ae.application_period)}</span>`:''}
        ${ae.purchase_requirement?`<span>购买条件</span><span>${esc(ae.purchase_requirement)}</span>`:''}
        ${ae.travel_feasibility?`<span>游客友好</span><span>${esc(ae.travel_feasibility)}</span>`:''}
      </div>
      ${item.short_summary_cn?`<p style="font-size:.84em;color:#555;margin-top:6px">${esc(item.short_summary_cn)}</p>`:''}
      ${ae.action_needed_cn?`<div class="action-line">🎯 ${esc(ae.action_needed_cn)}</div>`:''}
      ${item.why_it_matters_cn?`<p style="font-size:.82em;color:var(--muted);margin-top:4px">📌 ${esc(item.why_it_matters_cn)}</p>`:''}
      <a class="src-btn" href="${esc(link)}" target="_blank">📎 官方来源</a>
    </div>`;
  }).join('')+'</div>';
}

// ---- US MARKET IMPACT ----
function renderMarket(){
  const mi=DATA.us_market_impact||{};
  if(!mi.overall_market_tone){
    $('#market-section').style.display='none';
    return;
  }
  $('#market-section').style.display='block';
  const tone={
    positive:['g','🟢 偏正面 / Risk-On'],
    mixed:['y','🟡 混合 / Mixed'],
    negative:['r','🔴 偏负面 / Risk-Off'],
    neutral:['n','⚪ 中性'],
    sector_rotation:['y','🔄 板块轮动'],
    unclear:['n','❓ 不明确']
  };
  const[tc,tl]=tone[mi.overall_market_tone]||['n',mi.overall_market_tone||'?'];

  let h=`<h3>📈 美股影响分析 <span class="mkt-tone ${tc}">${tl}</span></h3>`;
  h+=`<p class="disc">⚠️ 以下内容仅用于信息整理，<b>不构成投资建议</b></p>`;
  h+=`<p class="mp-summary">${esc(mi.summary_cn||'')}</p>`;

  // Index impact
  const idx=mi.index_impact||{};
  h+=`<div class="mp-idx">`;
  if(idx.nasdaq)h+=`<span>Nasdaq <b>${esc(idx.nasdaq)}</b></span>`;
  if(idx.sp500)h+=`<span>S&P 500 <b>${esc(idx.sp500)}</b></span>`;
  if(idx.russell2000)h+=`<span>Russell 2000 <b>${esc(idx.russell2000)}</b></span>`;
  h+=`</div>`;

  // Key drivers
  if(mi.key_market_drivers&&mi.key_market_drivers.length){
    h+='<div class="mp-section"><h4>关键驱动因素</h4><ul>';
    mi.key_market_drivers.forEach(d=>h+=`<li style="list-style:disc;margin-left:16px;font-size:.84em">${esc(d)}</li>`);
    h+='</ul></div>';
  }

  // Sector impacts table
  if((mi.sector_impacts||[]).length){
    h+='<div class="mp-section"><h4>板块影响</h4><table class="mp-table"><thead><tr><th>板块</th><th>方向</th><th>原因</th></tr></thead><tbody>';
    mi.sector_impacts.forEach(s=>{
      const d=s.direction||'';
      const dc=d.includes('利好')||d.includes('up')||d.includes('正面')?'up'
        :d.includes('利空')||d.includes('down')||d.includes('负面')?'down':'mix';
      h+=`<tr><td><b>${esc(s.sector||'')}</b></td><td class="${dc}">${esc(d)}</td><td>${esc(s.reason_cn||'')}</td></tr>`;
    });
    h+='</tbody></table></div>';
  }

  // Theme impacts
  if((mi.theme_impacts||[]).length){
    h+='<div class="mp-section"><h4>主题观察</h4>';
    mi.theme_impacts.forEach(t=>{
      h+=`<p style="font-size:.85em;margin:6px 0;line-height:1.55"><b>${esc(t.theme||'')}</b> — ${esc(t.direction||'')}<br><span style="color:var(--muted)">${esc(t.reason_cn||'')}</span></p>`;
    });
    h+='</div>';
  }

  // Risk factors
  if((mi.risk_factors||[]).length){
    h+='<div class="mp-section"><h4>风险因素</h4><ul>';
    mi.risk_factors.forEach(r=>h+=`<li>${esc(r)}</li>`);
    h+='</ul></div>';
  }

  // Follow-up events
  if((mi.follow_up_events||[]).length){
    h+='<div class="mp-section"><h4>后续追踪事件</h4><table class="mp-table"><thead><tr><th>事件</th><th>预期日期</th><th>追踪原因</th></tr></thead><tbody>';
    mi.follow_up_events.forEach(e=>h+=`<tr><td><b>${esc(e.event_name||'')}</b></td><td>${esc(e.expected_date||'')}</td><td>${esc(e.why_watch_cn||'')}</td></tr>`);
    h+='</tbody></table></div>';
  }

  $('#market-panel').innerHTML=h;
}

// ---- WATCHLIST ----
function renderWatchlist(){
  if(!WATCHLIST.length){
    $('#watchlist-content').innerHTML='<p class="empty-state">暂无追踪事件</p>';
    return;
  }
  let h='<table class="wl-table"><thead><tr><th>事件</th><th>预期日期</th><th>紧急度</th><th>追踪原因</th><th>类型</th></tr></thead><tbody>';
  WATCHLIST.slice(0,25).forEach(w=>{
    const uc={high:'color:#dc2626;font-weight:700',medium:'color:#f59e0b;font-weight:600',low:'color:var(--muted)'};
    h+=`<tr>
      <td><b>${esc(w.title||'')}</b></td>
      <td>${esc(w.expected_date||'')}</td>
      <td style="${uc[w.urgency]||''}">${esc(w.urgency||'—')}</td>
      <td style="font-size:.82em">${esc(w.why_watch_cn||'')}</td>
      <td><span class="badge ca">${esc(w.category||'')}</span></td>
    </tr>`;
  });
  h+='</tbody></table>';
  $('#watchlist-content').innerHTML=h;
}

// ---- CHIPS ----
function initChips(){
  const chips=[
    ['📌 高重要', 'high'],
    ['⚡ 高紧急', 'urgent'],
    ['🎯 需行动', 'action'],
    ['📈 美股', 'market'],
    ['🎌 动漫', 'anime'],
    ['🎫 抽选/先着', 'lottery'],
    ['🆕 今日', 'recent'],
  ];
  $('#chips-row').innerHTML=chips.map(([l,k])=>`<span class="chip" data-chip="${k}">${l}</span>`).join('');
}

function updateChips(){
  $$('.chip').forEach(c=>c.classList.toggle('on',c.dataset.chip===fState.chip));
}

// ---- SETUP EVENTS ----
function setupEvents(){
  // Search
  let searchTimer;
  $('#search-input').addEventListener('input',e=>{
    clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>{
      fState.search=e.target.value.trim();
      renderCards();
    },250);
  });

  // Sort
  $('#sort-select').addEventListener('change',e=>{
    fState.sort=e.target.value;
    renderCards();
  });

  // Category
  $('#cat-select').addEventListener('change',e=>{
    fState.cat=e.target.value;
    fState.chip=null;
    updateChips();
    renderCards();
  });

  // Chips
  $$('.chip').forEach(c=>c.addEventListener('click',function(){
    if(fState.chip===this.dataset.chip){
      fState.chip=null;
    }else{
      fState.chip=this.dataset.chip;
    }
    fState.cat='all';
    $('#cat-select').value='all';
    updateChips();
    renderCards();
    $('#news-cards').scrollIntoView({behavior:'smooth',block:'start'});
  }));

  // BTT
  const btt=$('#btt');
  window.addEventListener('scroll',()=>{
    btt.style.display=window.scrollY>600?'flex':'none';
  },{passive:true});
  btt.addEventListener('click',()=>{
    window.scrollTo({top:0,behavior:'smooth'});
  });

  // Keyboard: ESC to clear all filters
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&document.activeElement!==$('#search-input')){
      fState.chip=null;fState.cat='all';fState.search='';
      $('#search-input').value='';$('#cat-select').value='all';
      updateChips();renderCards();
    }
  });
}

// ---- MAIN ----
async function main(){
  const ok=await loadData();
  if(!ok||!DATA){
    $('#loading-msg').innerHTML=`<div style="color:#dc2626;padding:40px;text-align:center">
      <p style="font-size:1.2em;font-weight:700;margin-bottom:8px">❌ 无法加载数据</p>
      <p style="color:var(--muted)">${window._loadError||'未知错误'}</p>
      <p style="margin-top:16px;font-size:.85em;color:var(--muted)">请先运行 <code>python main.py</code> 生成数据，然后刷新页面</p>
      <p style="font-size:.78em;color:var(--muted)">再执行 <code>cd site && python3 -m http.server 8080</code></p>
    </div>`;
    return;
  }

  $('#loading-msg').style.display='none';
  $('#main-content').style.display='block';

  // Render all sections
  renderHero();
  renderBrief();
  renderImpact();
  renderTop();
  renderMarket();
  renderAnime();
  renderWatchlist();

  // Toolbar & cards
  $('#toolbar-strip').style.display='block';
  initChips();
  renderCards();

  // Events
  setupEvents();

  // Update nav time
  const m=DATA.metadata||{};
  $('#nav-time').textContent='更新 '+((m.generated_at||'').split(' ').pop()||'—');

  // Footer
  $('#site-footer').innerHTML=`<p>JiaJia Daily 5.0 · Intelligence Edition · ${esc(m.report_date||'')}</p><p style="font-size:.72em;margin-top:4px">美股分析仅用于信息整理，不构成投资建议 · Powered by DeepSeek</p>`;
}

// Boot
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',main);else main();
})();
