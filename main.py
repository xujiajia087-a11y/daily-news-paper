#!/usr/bin/env python3
"""daily-news-paper v4.0 — Intelligence Edition
JiaJia Daily 情报日报 4.0
= 动漫/周边/签售追踪 + AI/科技/政治解读 + 美股影响分析 + 杂志排版 + 未来追踪
"""

import json, os, sys, time
from datetime import datetime, timezone, timedelta
from collections import Counter

# ---- macOS SSL 修复 ----
import ssl as _ssl
try:
    import certifi as _certifi
    _ssl._create_default_https_context = lambda: _ssl.create_default_context(cafile=_certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
except ImportError:
    pass

import feedparser, yaml, requests
from dotenv import load_dotenv
from article_fetcher import enrich_entry
from dedupe import deduplicate
from scorer import score_all, add_freshness, select_frontpage_ranked, detect_anime_event_fields

load_dotenv()

# ---- CONFIG ----
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_FILE = os.path.join(BASE_DIR, "feeds.yaml")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SITE_DATA_DIR = os.path.join(BASE_DIR, "site", "data")
for p in [OUTPUT_DIR]: os.makedirs(p, exist_ok=True)
MD_OUTPUT = os.path.join(OUTPUT_DIR, "daily-news.md")
JSON_OUTPUT_LEGACY = os.path.join(OUTPUT_DIR, "daily-news.json")
HTML_OUTPUT = os.path.join(OUTPUT_DIR, "daily-news.html")
JSON_OUTPUT = os.path.join(OUTPUT_DIR, "daily-news.json")
WATCHLIST_OUTPUT = os.path.join(OUTPUT_DIR, "watchlist.json")

CATEGORY_MAP = {
    "anime_collab": {"label": "动漫联名·IP合作", "icon": "🤝"},
    "merch_release": {"label": "新周边·限定发售·抽选", "icon": "🛍️"},
    "manga_signing_events": {"label": "漫画家签售·活动", "icon": "✍️"},
    "seiyuu_events": {"label": "声优见面会·活动", "icon": "🎤"},
    "japan_event_calendar": {"label": "日本活动日历·展览", "icon": "🗓️"},
    "ai_tech": {"label": "AI·科技·芯片", "icon": "🤖"},
    "politics_world": {"label": "政治·国际·政策", "icon": "🌍"},
}

TZ_PERTH = timezone(timedelta(hours=8))
MAX_PER_FEED, FRONTPAGE_COUNT, ARTICLE_BODY_MAX = 30, 8, 3000
REQUEST_TIMEOUT, USER_AGENT = 8, "daily-news-paper/4.0"
DEEPSEEK_MAX_INPUT, BODY_FETCH_LIMIT = 30, 15

def load_config():
    global MAX_PER_FEED, FRONTPAGE_COUNT, ARTICLE_BODY_MAX, REQUEST_TIMEOUT, USER_AGENT
    if not os.path.exists(FEEDS_FILE): sys.exit(f"[ERROR] 找不到 {FEEDS_FILE}")
    with open(FEEDS_FILE, encoding="utf-8") as f: data = yaml.safe_load(f)
    fc = data.get("fetch", {})
    for k, v in [("max_per_feed",30),("frontpage_count",8),("article_body_max_chars",3000),("request_timeout",8)]:
        globals()[k.upper() if k != "article_body_max_chars" else "ARTICLE_BODY_MAX"] = fc.get(k, v)
    USER_AGENT = fc.get("user_agent", USER_AGENT)
    return data

def flatten_feeds(config):
    feeds = []
    for cat_key, cat_data in config.get("categories", {}).items():
        for f in cat_data.get("feeds", []):
            if not f.get("enabled", True): continue
            feeds.append({**f, "_category": cat_key})
    return feeds

def fetch_all(feeds):
    entries, fstats = [], {}
    for fc in feeds:
        name, url, cat = fc.get("name","?"), fc.get("url",""), fc.get("_category","")
        print(f"  [{cat}] {name} ... ", end="", flush=True)
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"❌ {e}"); fstats[name] = 0; continue
        if parsed.bozo and not parsed.entries:
            print(f"❌ 0 (status={getattr(parsed,'status','?')})"); fstats[name] = 0; continue
        count = 0
        for e in parsed.entries:
            if count >= MAX_PER_FEED: break
            pub = e.get("published_parsed") or e.get("updated_parsed")
            dt_str = ""
            if pub:
                try:
                    dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(TZ_PERTH)
                    dt_str = dt.strftime("%Y-%m-%d %H:%M")
                except: pass
            entries.append({"title": e.get("title","").strip(), "link": e.get("link",""),
                "source": name, "source_display_name": fc.get("name", name),
                "source_cat": cat, "summary": (e.get("summary","") or e.get("description","")).strip(),
                "published": dt_str})
            count += 1
        print(f"✅ {count}"); fstats[name] = count
    return entries, fstats

# ---- DEEPSEEK v4 PROMPTS ----
def build_v4_items_prompt(entries):
    items_text = []
    for i, e in enumerate(entries):
        body = e.get("body", e.get("summary",""))[:400]
        ae = e.get("anime_event_fields", {})
        ae_str = ""
        if ae:
            ae_str = f"\n    活动字段: type={ae.get('event_type','')} ip={ae.get('ip_or_work','')} person={ae.get('person_name','')}"
        items_text.append(f"[{i+1}] {e['title']}\n    来源:{e.get('source_display_name',e['source'])} | {e.get('published','?')}\n    {e['link']}\n    提示:{e.get('category_hint','?')} | 评分:I={e.get('importance_score',5)} U={e.get('urgency_score',5)} C={e.get('collector_value',5)}{ae_str}\n    内容:{body}")
    return f"""你是 JiaJia Daily 情报日报主编。逐条处理新闻，输出 JSON 数组。

可用分类: {json.dumps({k:v['label'] for k,v in CATEGORY_MAP.items()}, ensure_ascii=False)}

每条输出:
- index, title_cn(≤30字), source, source_display_name, category, news_type(anime_event/tech/politics/general), date_display, freshness_label
- key_takeaway_cn(1句话重点,20-40字), short_summary_cn(2-4句), why_it_matters_cn
- action_suggestion_cn(具体可操作)
- importance_score(1-10), urgency_score(1-10), collector_value(1-10), tracking_value(1-10)
- editor_reason_cn, frontpage_reason_cn

如果是动漫/声优/签售/周边(anime_event):
- anime_event_detail: {{event_type, ip_or_work_title, person_name, role, event_date, event_time, venue, city, country, ticket_method, application_period, lottery_or_first_come, purchase_requirement, goods_or_bonus, official_source, urgency_level, collector_value, travel_feasibility, action_needed_cn}}
  字段填"未知"而非省略

如果是AI/科技/政治:
- impact_analysis: {{immediate_impact_cn(1-3天), medium_term_impact_cn(1-4周), long_term_impact_cn(3-12月), affected_sectors(list), affected_assets(list), us_stock_relevance(none/low/medium/high/very_high), market_sentiment(risk_on/risk_off/mixed/sector_rotation/unclear), risk_level(low/medium/high), follow_up_questions(list)}}
- us_market_relevance: none/low/medium/high/very_high

所有输出中文。新闻:
{items_text}

严格只返回JSON数组:"""

def build_v4_brief_prompt(results):
    items_text = []
    for r in results:
        items_text.append(f"- [{r.get('category','')}] {r.get('title_cn','')} | I={r.get('importance_score',5)} U={r.get('urgency_score',5)} | {r.get('key_takeaway_cn','')} | US={r.get('us_market_relevance','?')}")
    block = "\n".join(items_text)
    return f"""基于今日全部新闻，输出主编简报 JSON:

{{
  "daily_overview": {{
    "one_sentence_cn": "今天整体1-2句话(50-80字)",
    "market_mood_cn": "市场情绪概括",
    "anime_event_mood_cn": "动漫活动氛围概括(如实，无则说今日未发现高价值情报)",
    "what_to_watch_next_cn": "下一步关注什么"
  }},
  "impact_map": {{
    "anime_collecting": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}},
    "japanese_events": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}},
    "ai_tech": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}},
    "us_stocks": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}},
    "politics_risk": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}},
    "future_watchlist": {{"level":"low/medium/high","summary_cn":"","related_count":0,"representative":""}}
  }},
  "executive_brief": {{
    "top_5_judgements": ["判断1","..."],
    "anime_merch_signing_highlights": ["值得蹲1","..."],
    "ai_tech_highlights": ["科技1","..."],
    "politics_highlights": ["政治1","..."],
    "us_stock_market_impacts": ["美股影响1","..."],
    "future_watchlist": ["追踪1","..."],
    "noise_or_low_priority": ["噪音1","..."],
    "final_editor_note": "结束语"
  }},
  "us_market_impact": {{
    "overall_market_tone": "positive/mixed/negative/neutral",
    "summary_cn": "",
    "index_impact": {{"nasdaq":"","sp500":"","russell2000":""}},
    "sector_impacts": [{{"sector":"","direction":"up/down/mixed","reason_cn":"","related_news":"","possible_tickers":""}}],
    "theme_impacts": [{{"theme":"","direction":"up/down/mixed","reason_cn":"","watch_tickers":""}}],
    "risk_factors": [""],
    "follow_up_events": [{{"event_name":"","expected_date":"","why_watch_cn":"","market_relevance_cn":""}}]
  }},
  "future_watchlist": [{{"title":"","category":"","expected_date":"","why_watch_cn":"","market_relevance_cn":"","anime_relevance_cn":"","urgency":"high/medium/low"}}]
}}

中文、有判断、不模板化。内容不足时诚实说明。市场分析加免责"不构成投资建议"。
今日新闻:
{block}

严格只返回JSON:"""

def call_deepseek(prompt, label=""):
    if not DEEPSEEK_API_KEY:
        return [] if label == "items" else {}
    print(f"  [AI] {label} ... ", end="", flush=True)
    h = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    try:
        t0 = time.time()
        r = requests.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions", headers=h,
            json={"model":"deepseek-chat","messages":[{"role":"system","content":"你是 JiaJia Daily 情报日报主编，只输出合法 JSON。"},{"role":"user","content":prompt}],"temperature":0.3,"max_tokens":16384}, timeout=180)
        r.raise_for_status()
        c = r.json()["choices"][0]["message"]["content"].strip()
        if c.startswith("```"): c = "\n".join([l for l in c.split("\n") if not l.startswith("```")])
        result = json.loads(c)
        print(f"✅ {time.time()-t0:.1f}s"); return result
    except Exception as e:
        print(f"❌ {e}"); return [] if label == "items" else {}

def enrich_results(results, original):
    now = datetime.now(TZ_PERTH)
    for item in results:
        idx = item.get("index",0)-1
        if 0 <= idx < len(original): item["_original"] = original[idx]
        item["is_recent"], item["is_old_context"], item["freshness_label"] = False, False, "时间未知"
        pub = item.get("published_at","") or item.get("date_display","")
        if not item.get("date_display"): item["date_display"] = pub
        if pub:
            try:
                for fmt in ["%Y-%m-%d %H:%M","%Y-%m-%d"]:
                    try: pub_dt = datetime.strptime(pub,fmt).replace(tzinfo=TZ_PERTH); break
                    except: continue
                else: continue
                h = (now-pub_dt).total_seconds()/3600
                if h<=24: item["is_recent"]=True; item["freshness_label"]="今日新情报"
                elif h>72: item["is_old_context"]=True; item["freshness_label"]="旧闻/背景"
                else: item["freshness_label"]=f"{int(h)}h前"
            except: pass

def group_by_category(results):
    g = {k:[] for k in CATEGORY_MAP}
    for item in results:
        cat = item.get("category","")
        if cat in g: g[cat].append(item)
    for k in g: g[k] = g[k][:15]
    return g

def load_watchlist():
    if os.path.exists(WATCHLIST_OUTPUT):
        try:
            with open(WATCHLIST_OUTPUT, encoding="utf-8") as f: return json.load(f)
        except: pass
    return []

def update_watchlist(existing, new_items):
    now = datetime.now(TZ_PERTH).strftime("%Y-%m-%d")
    titles = {w.get("title","") for w in existing}
    for item in new_items:
        if item.get("title","") not in titles:
            item["created_at"] = now; item["updated_at"] = now; item["status"] = "active"
            existing.append(item)
            titles.add(item["title"])
    # Mark expired (>90 days)
    for w in existing:
        try:
            ed = w.get("expected_date","")
            if ed:
                dt = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=TZ_PERTH)
                if (datetime.now(TZ_PERTH)-dt).days > 90: w["status"] = "expired"
        except: pass
    return existing

# ---- HTML v4 MAGAZINE ----
def generate_html_v4(meta, brief, frontpage, grouped):
    import html as _h
    def e(s): return _h.escape(str(s)) if s else ""
    def badge(t,c=""): return f'<span class="badge {c}">{e(t)}</span>'

    def score_row(l,v):
        c = {9:"#dc2626",7:"#f97316",5:"#eab308",3:"#22c55e"}.get(max([k for k in [9,7,5,3] if v>=k] or [3]),"#3b82f6")
        return f'<span class="score"><em>{l}</em><b style="width:{min(v*10,100)}%;background:{c}"></b><strong>{v}</strong></span>'

    def market_badge(tone):
        m = {"positive":"🟢 偏正面","mixed":"🟡 混合","negative":"🔴 偏负面","neutral":"⚪ 中性"}
        return badge(m.get(tone,tone), f"mkt-{tone}")

    def anime_card(item):
        ae = item.get("anime_event_detail",{}) or {}
        return f"""<div class="event-card anime">
  <div class="ec-head">{badge(item.get("news_type","anime_event"),"type-anime")}{badge("来源:"+e(item.get("source_display_name","?")),"src")}<span class="dt">{e(item.get("date_display","?"))}</span>{badge(item.get("freshness_label",""),"fr")}</div>
  <h3><a href="{e(item.get('original_link','#'))}">{e(item.get('title_cn','?'))}</a></h3>
  <div class="ec-detail">
    <div class="ec-row"><span>类型</span><span>{e(ae.get('event_type','未知'))}</span></div>
    <div class="ec-row"><span>作品/IP</span><span>{e(ae.get('ip_or_work_title','未知'))}</span></div>
    <div class="ec-row"><span>人物</span><span>{e(ae.get('person_name','未知'))} ({e(ae.get('role','未知'))})</span></div>
    <div class="ec-row"><span>日期·时间</span><span>{e(ae.get('event_date','?'))} {e(ae.get('event_time','?'))}</span></div>
    <div class="ec-row"><span>地点</span><span>{e(ae.get('venue','?'))} {e(ae.get('city',''))} {e(ae.get('country',''))}</span></div>
    <div class="ec-row"><span>票务</span><span>{e(ae.get('ticket_method','未知'))} | {e(ae.get('lottery_or_first_come','未知'))}</span></div>
    <div class="ec-row"><span>応募期間</span><span>{e(ae.get('application_period','未知'))}</span></div>
    <div class="ec-row"><span>购买条件</span><span>{e(ae.get('purchase_requirement','未知'))}</span></div>
    <div class="ec-row"><span>特典/周边</span><span>{e(ae.get('goods_or_bonus','未知'))}</span></div>
  </div>
  <div class="scores">{score_row("重要性",item.get("importance_score",5))}{score_row("紧急度",item.get("urgency_score",5))}{score_row("收藏价值",item.get("collector_value",5))}</div>
  <div class="takeaway">💡 {e(item.get("key_takeaway_cn",""))}</div>
  <div class="action-box">🎯 行动建议: {e(ae.get("action_needed_cn",item.get("action_suggestion_cn","")))} | 游客友好: {e(ae.get("travel_feasibility","未知"))}</div>
  <a class="src-link" href="{e(item.get('original_link','#'))}">📎 {e(ae.get('official_source','查看原文'))}</a>
</div>"""

    def tech_card(item):
        ia = item.get("impact_analysis",{}) or {}
        return f"""<div class="event-card tech">
  <div class="ec-head">{badge(item.get("news_type","tech"),"type-tech")}{badge("来源:"+e(item.get("source_display_name","?")),"src")}<span class="dt">{e(item.get("date_display","?"))}</span></div>
  <h3><a href="{e(item.get('original_link','#'))}">{e(item.get('title_cn','?'))}</a></h3>
  <div class="scores">{score_row("重要性",item.get("importance_score",5))}{score_row("追踪价值",item.get("tracking_value",5))}</div>
  <div class="takeaway">💡 {e(item.get("key_takeaway_cn",""))}</div>
  <p>{e(item.get("short_summary_cn",""))}</p>
  <p class="why">📌 {e(item.get("why_it_matters_cn",""))}</p>
  <div class="impact-grid">
    <div><span>短期(1-3天)</span><span>{e(ia.get("immediate_impact_cn","未知"))}</span></div>
    <div><span>中期(1-4周)</span><span>{e(ia.get("medium_term_impact_cn","未知"))}</span></div>
    <div><span>长期(3-12月)</span><span>{e(ia.get("long_term_impact_cn","未知"))}</span></div>
  </div>
  <div class="meta-row"><span>影响板块</span><span>{e(", ".join(ia.get("affected_sectors",[]) or ["未知"]))}</span></div>
  <div class="meta-row"><span>相关资产</span><span>{e(", ".join(ia.get("affected_assets",[]) or ["未知"]))}</span></div>
  <div class="meta-row"><span>美股相关性</span>{badge(e(ia.get("us_stock_relevance","none")),"mkt")}</div>
  <div class="meta-row"><span>市场情绪</span>{badge(e(ia.get("market_sentiment","unclear")),"mkt")}</div>
  <div class="meta-row"><span>风险等级</span>{badge(e(ia.get("risk_level","medium")),"risk")}</div>
  <a class="src-link" href="{e(item.get('original_link','#'))}">📎 查看原文</a>
</div>"""

    def general_card(item):
        return f"""<div class="event-card general">
  <div class="ec-head">{badge(item.get("news_type","general"),"type-general")}{badge("来源:"+e(item.get("source_display_name","?")),"src")}<span class="dt">{e(item.get("date_display","?"))}</span>{badge(item.get("freshness_label",""),"fr")}</div>
  <h3><a href="{e(item.get('original_link','#'))}">{e(item.get('title_cn','?'))}</a></h3>
  <div class="scores">{score_row("重要性",item.get("importance_score",5))}{score_row("追踪价值",item.get("tracking_value",5))}</div>
  <div class="takeaway">💡 {e(item.get("key_takeaway_cn",""))}</div>
  <p>{e(item.get("short_summary_cn",""))}</p>
  <div class="action-box">🎯 {e(item.get("action_suggestion_cn",""))}</div>
  <a class="src-link" href="{e(item.get('original_link','#'))}">📎 查看原文</a>
</div>"""

    def render_card(item):
        nt = item.get("news_type","")
        if nt == "anime_event": return anime_card(item)
        if nt in ("tech","politics"): return tech_card(item)
        return general_card(item)

    # ---- IMPACT MAP GRID ----
    im = brief.get("impact_map",{})
    def impact_cell(key, label, icon):
        d = im.get(key,{})
        lvl = d.get("level","low")
        lc = {"high":"#dc2626","medium":"#f59e0b","low":"#22c55e"}.get(lvl,"#888")
        return f"""<div class="im-cell" style="border-top:3px solid {lc}">
  <div class="im-icon">{icon}</div><div class="im-label">{label}</div>
  <div class="im-level" style="color:{lc}">{lvl.upper()}</div>
  <div class="im-text">{e(d.get('summary_cn',''))}</div>
  <div class="im-count">{d.get('related_count',0)}条相关</div>
</div>"""

    # ---- EXECUTIVE BRIEF ----
    eb = brief.get("executive_brief",{})
    def eb_section(title, items):
        if not items: return ""
        return f"<h4>{title}</h4><ul>"+"".join(f"<li>{e(i)}</li>" for i in items)+"</ul>"

    # ---- MARKET IMPACT ----
    mi = brief.get("us_market_impact",{})
    def market_section():
        if not mi: return ""
        rows = ""
        for s in mi.get("sector_impacts",[]):
            rows += f"<tr><td>{e(s.get('sector','?'))}</td><td>{e(s.get('direction','?'))}</td><td>{e(s.get('reason_cn',''))}</td></tr>"
        themes = ""
        for t in mi.get("theme_impacts",[]):
            themes += f"<div class='theme-row'><span class='t-name'>{e(t.get('theme','?'))}</span><span class='t-dir'>{e(t.get('direction','?'))}</span><span class='t-reason'>{e(t.get('reason_cn',''))}</span></div>"
        risks = "".join(f"<li>{e(r)}</li>" for r in mi.get("risk_factors",[]))
        follow = ""
        for fe in mi.get("follow_up_events",[]):
            follow += f"<tr><td>{e(fe.get('event_name','?'))}</td><td>{e(fe.get('expected_date','?'))}</td><td>{e(fe.get('why_watch_cn',''))}</td></tr>"
        return f"""<div class="market-module">
  <div class="mm-header">{market_badge(mi.get('overall_market_tone','neutral'))}<span>美股影响分析</span></div>
  <p>⚠️ 以下分析仅用于信息整理，<strong>不构成投资建议</strong>。</p>
  <p class="mm-summary">{e(mi.get('summary_cn',''))}</p>
  <div class="index-row"><span>Nasdaq</span><span>{e(mi.get('index_impact',{}).get('nasdaq','?'))}</span><span>S&P500</span><span>{e(mi.get('index_impact',{}).get('sp500','?'))}</span><span>Russell</span><span>{e(mi.get('index_impact',{}).get('russell2000','?'))}</span></div>
  <h4>板块影响</h4><table class="mm-table"><tr><th>板块</th><th>方向</th><th>原因</th></tr>{rows}</table>
  <h4>主题观察</h4>{themes}
  <h4>风险因素</h4><ul>{risks}</ul>
  <h4>后续追踪事件</h4><table class="mm-table"><tr><th>事件</th><th>预期日期</th><th>关注原因</th></tr>{follow}</table>
</div>"""

    # ---- WATCHLIST ----
    wl = brief.get("future_watchlist",[])
    def watchlist_section():
        if not wl: return '<p class="empty">今日无新增追踪事件。</p>'
        rows = ""
        for w in wl:
            rows += f"<tr><td>{e(w.get('title','?'))}</td><td>{e(w.get('category','?'))}</td><td>{e(w.get('expected_date','?'))}</td><td>{badge(e(w.get('urgency','medium')),'urg-'+e(w.get('urgency','medium')))}</td><td>{e(w.get('why_watch_cn',''))}</td></tr>"
        return f"<table class='wl-table'><tr><th>事件</th><th>类型</th><th>预期日期</th><th>紧急</th><th>关注原因</th></tr>{rows}</table>"

    do = brief.get("daily_overview",{})

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>JiaJia Daily 情报日报 4.0</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:#f8f8f6;color:#1a1a1a;line-height:1.65}}
.wrap{{max-width:1200px;margin:0 auto;padding:0 24px}}

/* MASTHEAD */
.mast{{background:linear-gradient(135deg,#0f0f1a 0%,#1a1a2e 40%,#16213e 100%);color:#fff;padding:32px 24px 20px;text-align:center}}
.mast h1{{font-size:2.2em;font-weight:900;letter-spacing:.06em}}
.mast .ver{{font-size:.85em;opacity:.7;margin:4px 0}}
.mast .dline{{font-size:1.1em;margin:8px 0;opacity:.9}}
.mast .sline{{display:flex;justify-content:center;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:.78em;opacity:.75}}
.mast .sline span{{background:rgba(255,255,255,.1);padding:3px 10px;border-radius:4px}}

/* DAILY OVERVIEW */
.daily-ov{{background:linear-gradient(135deg,#eff6ff,#dbeafe);border:1px solid #93c5fd;border-radius:10px;padding:18px 22px;margin:24px 0;font-size:1.02em;color:#1e40af;font-weight:500;line-height:1.7}}
.daily-ov b{{color:#1e3a5f}}

/* IMPACT MAP */
.im-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:24px 0}}
.im-cell{{background:#fff;border-radius:8px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.im-icon{{font-size:1.4em}}
.im-label{{font-size:.82em;color:#555;margin:4px 0}}
.im-level{{font-size:.75em;font-weight:800;margin-bottom:4px}}
.im-text{{font-size:.8em;color:#555;line-height:1.5}}
.im-count{{font-size:.72em;color:#999;margin-top:6px}}

/* SECTION */
.sec{{margin:32px 0}}
.sec-title{{font-size:1.15em;font-weight:800;padding:8px 0;border-bottom:2px solid #1a1a2e;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.sec-title.red{{color:#dc2626;border-color:#dc2626}}

/* EXEC BRIEF */
.eb{{background:#fffbeb;border:2px solid #f59e0b;border-radius:12px;padding:22px 26px;margin:24px 0}}
.eb h2{{color:#92400e;margin-bottom:12px;font-size:1.2em}}
.eb h4{{color:#92400e;margin:10px 0 4px;font-size:.95em}}
.eb ul{{list-style:none;padding:0}}
.eb li{{padding:3px 0 3px 16px;position:relative;color:#78350f;font-size:.88em}}
.eb li::before{{content:"▸";position:absolute;left:0;color:#f59e0b}}

/* CARDS */
.event-card{{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.event-card.anime{{border-left:4px solid #8b5cf6}}
.event-card.tech{{border-left:4px solid #3b82f6}}
.event-card.general{{border-left:4px solid #d1d5db}}
.ec-head{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px;font-size:.78em}}
.event-card h3{{font-size:1.05em;margin:6px 0}}
.event-card h3 a{{color:#1a1a2e;text-decoration:none}}
.event-card h3 a:hover{{color:#2563eb}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.78em;font-weight:600}}
.type-anime{{background:#ede9fe;color:#7c3aed}}
.type-tech{{background:#dbeafe;color:#2563eb}}
.type-general{{background:#f3f4f6;color:#6b7280}}
.src{{background:#f0f0f0;color:#555}}
.fr{{background:#dcfce7;color:#166534}}
.mkt-positive{{background:#dcfce7;color:#166534}}
.mkt-negative{{background:#fee2e2;color:#991b1b}}
.mkt-mixed{{background:#fef3c7;color:#92400e}}
.mkt-neutral{{background:#f3f4f6;color:#6b7280}}
.risk{{background:#fee2e2;color:#991b1b}}
.dt{{color:#888;font-size:.85em}}

.ec-detail{{display:grid;grid-template-columns:1fr 2fr;gap:4px 12px;margin:8px 0;font-size:.82em}}
.ec-detail .ec-row{{display:contents}}
.ec-detail .ec-row span:first-child{{color:#888;font-weight:500}}
.ec-detail .ec-row span:last-child{{color:#333}}

.scores{{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0;font-size:.8em}}
.score{{display:inline-flex;align-items:center;gap:4px}}
.score em{{color:#888;font-style:normal;min-width:55px;font-size:.85em}}
.score b{{display:inline-block;width:64px;height:5px;background:#e5e7eb;border-radius:3px;position:relative;overflow:hidden}}
.score strong{{font-weight:700;color:#333;font-size:.85em}}

.takeaway{{background:#eff6ff;border-left:3px solid #3b82f6;padding:8px 12px;margin:8px 0;border-radius:0 6px 6px 0;font-size:.88em;color:#1e40af;font-weight:600}}
.action-box{{background:#fef3c7;border-radius:6px;padding:8px 12px;margin:6px 0;font-size:.85em;color:#92400e}}
.src-link{{display:inline-block;margin-top:6px;color:#2563eb;font-size:.83em;text-decoration:none;font-weight:600}}
.src-link:hover{{text-decoration:underline}}

.impact-grid{{display:grid;grid-template-columns:1fr;gap:6px;margin:8px 0;font-size:.84em}}
.impact-grid div{{display:flex;gap:8px}}
.impact-grid div span:first-child{{color:#888;min-width:80px;font-weight:500}}
.meta-row{{display:flex;gap:8px;font-size:.84em;margin:3px 0}}
.meta-row span:first-child{{color:#888;min-width:70px;font-weight:500}}

/* MARKET MODULE */
.market-module{{background:#fff;border:2px solid #2563eb;border-radius:12px;padding:22px 26px;margin:24px 0}}
.mm-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px;font-size:1.1em;font-weight:700}}
.mm-summary{{font-size:.92em;color:#555;margin:8px 0}}
.index-row{{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0;font-size:.85em}}
.index-row span:nth-child(odd){{color:#888;font-weight:600}}
.index-row span:nth-child(even){{color:#333}}
.mm-table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:.84em}}
.mm-table th,.mm-table td{{border:1px solid #e5e5e0;padding:6px 10px;text-align:left}}
.mm-table th{{background:#f9fafb;font-weight:600}}
.theme-row{{display:flex;gap:12px;padding:4px 0;font-size:.85em;align-items:center}}
.t-name{{font-weight:600;min-width:90px}}
.t-dir{{min-width:50px;font-size:.8em}}
.market-module h4{{font-size:.92em;margin:12px 0 4px;color:#333}}

/* WATCHLIST */
.wl-table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:.84em}}
.wl-table th,.wl-table td{{border:1px solid #e5e5e0;padding:6px 10px;text-align:left}}
.wl-table th{{background:#f9fafb;font-weight:600}}
.urg-high{{background:#fee2e2;color:#991b1b}}
.urg-medium{{background:#fef3c7;color:#92400e}}
.urg-low{{background:#f3f4f6;color:#6b7280}}

.foot{{text-align:center;color:#aaa;font-size:.78em;margin:40px 0 30px;padding-top:20px;border-top:1px solid #e5e5e0}}
.empty{{color:#999;font-style:italic;padding:8px 0;font-size:.88em}}

@media(max-width:768px){{
  .im-grid{{grid-template-columns:1fr 1fr}}
  .mast h1{{font-size:1.5em}}
  .ec-detail{{grid-template-columns:1fr}}
  .scores{{flex-direction:column;gap:4px}}
}}
</style></head><body>
<div class="mast">
  <h1>📰 JiaJia Daily 情报日报</h1>
  <div class="ver">4.0 Intelligence Edition</div>
  <div class="dline">{e(meta.get('report_date',''))} {e(meta.get('report_weekday',''))} · {e(meta.get('generated_at',''))} ({e(meta.get('timezone',''))})</div>
  <div class="sline">
    <span>📥 抓取 {meta.get('total_fetched',0)}</span><span>🔍 去重后 {meta.get('after_dedupe',0)}</span><span>✨ 入选 {meta.get('selected_count',0)}</span>
    <span>🎌 动漫/活动 {meta.get('anime_event_count',0)}</span><span>📈 美股相关 {meta.get('market_related_count',0)}</span><span>🔭 追踪 {meta.get('watchlist_count',0)}</span>
  </div>
</div>
<div class="wrap">

<!-- DAILY OVERVIEW -->
<div class="daily-ov"><b>📋 今日一句话总览：</b>{e(do.get('one_sentence_cn',''))}<br>
  <span style="font-size:.88em;opacity:.8">市场情绪: {e(do.get('market_mood_cn',''))} | 动漫活动: {e(do.get('anime_event_mood_cn',''))} | 下一步: {e(do.get('what_to_watch_next_cn',''))}</span>
</div>

<!-- IMPACT MAP -->
<div class="sec"><div class="sec-title">🗺️ 今日影响地图 Impact Map</div>
<div class="im-grid">
{impact_cell("anime_collecting","动漫·收藏","🎌")}
{impact_cell("japanese_events","日本线下活动","🗾")}
{impact_cell("ai_tech","AI·科技","🤖")}
{impact_cell("us_stocks","美股市场","📈")}
{impact_cell("politics_risk","政治风险","🌍")}
{impact_cell("future_watchlist","后续追踪","🔭")}
</div></div>

<!-- EXECUTIVE BRIEF -->
<div class="eb"><h2>📋 今日核心简报 Executive Brief</h2>
{eb_section("📌 今日最重要的5条判断",eb.get("top_5_judgements",[]))}
{eb_section("🎌 今日最值得蹲的动漫/周边/签售",eb.get("anime_merch_signing_highlights",[]))}
{eb_section("🤖 今日最值得关注的AI/科技",eb.get("ai_tech_highlights",[]))}
{eb_section("🌍 今日最值得关注的政治/全球",eb.get("politics_highlights",[]))}
{eb_section("📈 今日美股最重要影响",eb.get("us_stock_market_impacts",[]))}
{eb_section("🔭 未来7-30天持续追踪",eb.get("future_watchlist",[]))}
{eb_section("🔇 噪音/低优先级",eb.get("noise_or_low_priority",[]))}
<p style="color:#92400e;margin-top:10px;font-style:italic">✒️ {e(eb.get('final_editor_note',''))}</p>
</div>

<!-- TOP STORIES -->
<div class="sec"><div class="sec-title red">🔴 今日头版重点 Top Stories</div>"""
    for i, item in enumerate(frontpage):
        item["frontpage_rank"] = i+1
        html += render_card(item)
    html += "</div>"

    # ---- ANIME EVENTS ----
    anime_cats = ["anime_collab","merch_release","manga_signing_events","seiyuu_events","japan_event_calendar"]
    anime_items = []
    for ck in anime_cats:
        anime_items.extend(grouped.get(ck,[]))
    if anime_items:
        html += '<div class="sec"><div class="sec-title">🎌 动漫 / 周边 / 签售活动情报</div>'
        for item in anime_items:
            html += render_card(item)
        html += '</div>'

    # ---- AI/TECH ----
    if grouped.get("ai_tech"):
        html += '<div class="sec"><div class="sec-title">🤖 AI / 科技情报</div>'
        for item in grouped["ai_tech"]:
            html += render_card(item)
        html += '</div>'

    # ---- POLITICS ----
    if grouped.get("politics_world"):
        html += '<div class="sec"><div class="sec-title">🌍 政治 / 全球事件</div>'
        for item in grouped["politics_world"]:
            html += render_card(item)
        html += '</div>'

    # ---- MARKET IMPACT ----
    html += '<div class="sec"><div class="sec-title">📈 美股影响分析 US Market Impact</div>'
    html += market_section() + '</div>'

    # ---- WATCHLIST ----
    html += '<div class="sec"><div class="sec-title">🔭 未来追踪 Watchlist</div>'
    html += watchlist_section() + '</div>'

    html += f'<div class="foot">JiaJia Daily 情报日报 4.0 Intelligence Edition · {e(meta.get("report_date",""))} · 自动生成 · 不构成投资建议</div></div></body></html>'
    return html

# ---- MD v4 ----
def generate_md_v4(meta, brief, frontpage, grouped):
    lines = [f"# 📰 JiaJia Daily 情报日报 4.0", "",
             f"**{meta.get('report_date','')} {meta.get('report_weekday','')}** · {meta.get('generated_at','')} ({meta.get('timezone','')})",
             f"📥 {meta.get('total_fetched',0)} · 🔍 {meta.get('after_dedupe',0)} · ✨ {meta.get('selected_count',0)} · 🎌 {meta.get('anime_event_count',0)} · 📈 {meta.get('market_related_count',0)}",
             "", "---", ""]
    do = brief.get("daily_overview",{})
    lines += ["## 📋 今日一句话总览", "", f"> {do.get('one_sentence_cn','')}", ""]
    lines += ["## 🗺️ 今日影响地图", ""]
    im = brief.get("impact_map",{})
    for k,lab in [("anime_collecting","🎌 动漫收藏"),("japanese_events","🗾 日本活动"),("ai_tech","🤖 AI科技"),("us_stocks","📈 美股"),("politics_risk","🌍 政治"),("future_watchlist","🔭 追踪")]:
        d = im.get(k,{})
        lines.append(f"- **{lab}** [{d.get('level','low').upper()}]: {d.get('summary_cn','')} ({d.get('related_count',0)}条)")
    lines.append("")
    eb = brief.get("executive_brief",{})
    lines += ["---", "", "## 📋 今日核心简报 Executive Brief", ""]
    for sec,title in [("top_5_judgements","📌 5条判断"),("anime_merch_signing_highlights","🎌 值得蹲"),("ai_tech_highlights","🤖 AI科技"),("politics_highlights","🌍 政治"),("us_stock_market_impacts","📈 美股影响"),("future_watchlist","🔭 追踪")]:
        items = eb.get(sec,[])
        if items: lines += [f"### {title}",""]+[f"- {x}" for x in items]+[""]
    lines += [f"*✒️ {eb.get('final_editor_note','')}*", ""]
    lines += ["---", "", "## 🔴 今日头版重点", ""]
    for item in frontpage:
        lines += [f"### {item.get('title_cn','?')}", f"- 来源: {item.get('source_display_name','')} | {item.get('date_display','')}", f"- 💡 {item.get('key_takeaway_cn','')}", f"- {item.get('short_summary_cn','')}", f"- 🎯 {item.get('action_suggestion_cn','')}", f"- [原文]({item.get('original_link','#')})", ""]
    return "\n".join(lines)

# ---- JSON v4 ----
def generate_json_v4(meta, brief, frontpage, grouped, watchlist):
    def clean(item): return {k:v for k,v in item.items() if k!="_original"}
    return {"metadata":meta,"daily_overview":brief.get("daily_overview",{}),"impact_map":brief.get("impact_map",{}),
        "executive_brief":brief.get("executive_brief",{}),"top_stories":[clean(f) for f in frontpage],
        "anime_event_highlights":[clean(i) for ck in ["anime_collab","merch_release","manga_signing_events","seiyuu_events","japan_event_calendar"] for i in grouped.get(ck,[])],
        "ai_tech_highlights":[clean(i) for i in grouped.get("ai_tech",[])],
        "politics_highlights":[clean(i) for i in grouped.get("politics_world",[])],
        "us_market_impact":brief.get("us_market_impact",{}),"future_watchlist":brief.get("future_watchlist",[]),"articles":[clean(i) for ck in CATEGORY_MAP for i in grouped.get(ck,[])]}

# ---- MAIN ----
def main():
    now = datetime.now(TZ_PERTH)
    print(f"\n╔══════════════════════════════════╗\n║  JiaJia Daily 情报日报 4.0       ║\n║  Intelligence Edition            ║\n╚══════════════════════════════════╝")
    print(f"{now.strftime('%Y年%m月%d日')} {['一','二','三','四','五','六','日'][now.weekday()]}星期{['一','二','三','四','五','六','日'][now.weekday()]} | Australia/Perth\n")

    config = load_config(); feeds = flatten_feeds(config)
    print(f"[config] {len(feeds)} feeds\n[stage 1] RSS fetch ─────")
    raw, fstats = fetch_all(feeds)
    print(f"[feeds] total={len(raw)}\n[stage 2] Dedup ─────")
    entries, dup = deduplicate(raw)
    print(f"[dedupe] raw={len(raw)} after={len(entries)} duplicates={dup}\n")

    if not entries:
        print("[info] No entries."); return

    print("[stage 3] Body fetch ─────")
    bc = 0
    for e in entries[:BODY_FETCH_LIMIT]:
        if not e.get("body"): enrich_entry(e,timeout=REQUEST_TIMEOUT,user_agent=USER_AGENT)
        if e.get("body_source")=="fetched": bc+=1
    print(f"[body] {bc}/{min(BODY_FETCH_LIMIT,len(entries))}\n[stage 4] Score + anime detect ─────")
    entries = score_all(entries); entries = add_freshness(entries)
    # Detect anime event fields
    anime_count = 0
    for e in entries:
        af = detect_anime_event_fields(e)
        if af and af.get("event_type"): anime_count += 1; e["anime_event_fields"] = af
    print(f"[anime-events] {anime_count} candidates\n")
    sorted_e = sorted(entries, key=lambda e:(e.get("importance_score",0)*3+e.get("urgency_score",0)*2+e.get("collector_value",0)),reverse=True)
    di = sorted_e[:DEEPSEEK_MAX_INPUT]
    print(f"[score] {len(entries)} scored, {len(di)} → AI\n[stage 5] AI items ─────")
    results = call_deepseek(build_v4_items_prompt(di), "items")
    if not results: print("[warn] AI failed"); return
    enrich_results(results, di)
    print(f"[ai] {len(results)} items\n[stage 6] AI brief ─────")
    brief = call_deepseek(build_v4_brief_prompt(results), "brief")
    if not isinstance(brief, dict): brief = {}
    print(f"[brief] {'OK' if brief else 'empty'}\n[stage 7] Group ─────")
    grouped = group_by_category(results)
    for ck, items in grouped.items():
        print(f"  [{ck}] {CATEGORY_MAP[ck]['icon']} {CATEGORY_MAP[ck]['label']}: {len(items)}")
    # Stats
    frontpage = select_frontpage_ranked(results, FRONTPAGE_COUNT)
    market_count = sum(1 for r in results if r.get("us_market_relevance","") in ("high","very_high","medium"))
    wl = brief.get("future_watchlist",[])
    existing_wl = load_watchlist()
    updated_wl = update_watchlist(existing_wl, wl)
    meta = {
        "report_title":"JiaJia Daily 情报日报","report_date":now.strftime("%Y年%m月%d日"),
        "report_weekday":["星期一","星期二","星期三","星期四","星期五","星期六","星期日"][now.weekday()],
        "generated_at":now.strftime("%Y-%m-%d %H:%M"),"timezone":"Australia/Perth (UTC+8)",
        "data_window":"24h新闻 + 7d市场事件 + 90d动漫活动","total_fetched":len(raw),
        "after_dedupe":len(entries),"selected_count":len(results),"frontpage_count":len(frontpage),
        "anime_event_count":anime_count,"market_related_count":market_count,"watchlist_count":len(updated_wl)
    }

    print(f"\n[anime-events] {anime_count} candidates → {sum(len(grouped.get(ck,[])) for ck in ['anime_collab','merch_release','manga_signing_events','seiyuu_events','japan_event_calendar'])} selected")
    print(f"[market] {market_count} market-related items")
    print(f"[watchlist] active={sum(1 for w in updated_wl if w.get('status')=='active')} new={len(wl)} total={len(updated_wl)}")
    print("\n[output] ─────")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(SITE_DATA_DIR, exist_ok=True)
    with open(HTML_OUTPUT,"w",encoding="utf-8") as f: f.write(generate_html_v4(meta,brief,frontpage,grouped))
    print(f"[output] HTML → {HTML_OUTPUT}")
    with open(MD_OUTPUT,"w",encoding="utf-8") as f: f.write(generate_md_v4(meta,brief,frontpage,grouped))
    print(f"[output] MD   → {MD_OUTPUT}")
    # Site data (primary)
    site_json = generate_json_v4(meta,brief,frontpage,grouped,updated_wl)
    with open(os.path.join(SITE_DATA_DIR, "daily-news.json"),"w",encoding="utf-8") as f: json.dump(site_json,f,ensure_ascii=False,indent=2)
    print(f"[output] SITE JSON → site/data/daily-news.json")
    with open(os.path.join(SITE_DATA_DIR, "watchlist.json"),"w",encoding="utf-8") as f: json.dump(updated_wl,f,ensure_ascii=False,indent=2)
    print(f"[output] SITE WL   → site/data/watchlist.json")
    # Legacy JSON
    with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(site_json,f,ensure_ascii=False,indent=2)
    print(f"[output] JSON → {JSON_OUTPUT}")
    with open(WATCHLIST_OUTPUT,"w",encoding="utf-8") as f: json.dump(updated_wl,f,ensure_ascii=False,indent=2)
    print(f"[output] WATCHLIST → {WATCHLIST_OUTPUT}")
    total = sum(len(v) for v in grouped.values())
    print(f"\n╔══════════════════════════════════╗\n║  ✅ v4.0 完成！共 {total} 条新闻     ║\n╚══════════════════════════════════╝")

if __name__ == "__main__": main()
