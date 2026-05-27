#!/usr/bin/env python3
"""scorer.py — 新闻重要性 / 紧急度 / 收藏价值评分模块

评分规则：
- 限定、抽选、截止、今日发售、售票开始 → urgency 高
- 知名 IP、热门动漫、声优、漫画家、限量周边 → collector_value 高
- OpenAI、DeepSeek、Google、NVIDIA、Anthropic、重大模型 → importance 高
- 战争、选举、制裁、利率、外交冲突、政府政策 → importance 高
"""

import re
from typing import Optional


# ---- 关键词词典 ----
URGENCY_KEYWORDS = [
    "限定", "限量", "抽选", "截止", "今日发售", "售票开始", "预售",
    "最后机会", "即将截止", "倒计时", "发售日", "秒杀", "抢购",
    "limited", "deadline", "closing soon", "last chance", "preorder",
    "售罄", "sold out", "lottery", "一番赏",
]

COLLECTOR_KEYWORDS = [
    "手办", "figure", "谷子", "goods", "周边", "merchandise",
    "限定版", "limited edition", "collection", "collector",
    "Nendoroid", "黏土人", "Figma", "POP UP PARADE",
    "一番赏", "ichiban kuji", "一番くじ",
    "初音", "hololive", "鬼灭", "咒术", "间谍过家家", "葬送的芙莉莲",
    "海贼王", "one piece", "EVA", "新世纪福音战士",
    "JoJo", "Fate", "宝可梦", "Pokémon", "原神", "Genshin",
    "Aniplex", "Good Smile", "Bandai", "万代",
    "GUNDAM", "高达",
]

IMPORTANCE_HIGH_KEYWORDS = [
    "OpenAI", "DeepSeek", "Google", "NVIDIA", "Anthropic", "Meta",
    "Microsoft", "Apple", "GPT-5", "GPT-4", "Gemini", "Claude",
    "ChatGPT", "大模型", "LLM", "AGI",
    "战争", "war", "选举", "election", "制裁", "sanctions",
    "利率", "interest rate", "央行", "FED", "federal reserve",
    "外交", "diplomacy", "冲突", "conflict", "入侵", "invasion",
    "政府", "government", "政策", "policy", "白宫", "white house",
    "北约", "NATO", "欧盟", "EU", "联合国", "UN",
]

# 知名动漫 IP 关键词
ANIME_IP_KEYWORDS = [
    "龙珠", "Dragon Ball", "火影", "Naruto", "海贼王", "One Piece",
    "鬼灭之刃", "Demon Slayer", "咒术回战", "Jujutsu Kaisen",
    "间谍过家家", "Spy x Family", "葬送的芙莉莲", "Frieren",
    "进击的巨人", "Attack on Titan", "链锯人", "Chainsaw Man",
    "EVA", "Evangelion", "Fate", "JoJo", "钢炼", "Fullmetal",
    "宝可梦", "Pokémon", "初音未来", "hololive",
    "GUNDAM", "高达", "刀剑神域", "SAO", "Re:Zero",
    "推しの子", "Oshi no Ko", "胆大党", "Dan Da Dan",
    "呪術廻戦", "SPY×FAMILY", "葬送のフリーレン",
]


def score_entry(entry: dict) -> dict:
    """对单条新闻进行评分。

    Args:
        entry: 新闻条目字典，至少包含 title, body, source

    Returns:
        添加了 importance_score, urgency_score, collector_value,
        category_hint, tags, reason_for_score 等字段的条目
    """
    text = (
        (entry.get("title", "") + " " + entry.get("body", "") + " " + entry.get("source", ""))
        .lower()
    )
    title_lower = entry.get("title", "").lower()

    # ---- 紧急度评分 (1-10) ----
    urgency = 1
    for kw in URGENCY_KEYWORDS:
        if kw.lower() in text:
            urgency += 2
            if urgency > 10:
                urgency = 10
    if urgency < 3:
        urgency = 3  # 默认至少 3

    # ---- 收藏价值评分 (1-10) ----
    collector = 1
    for kw in COLLECTOR_KEYWORDS:
        if kw.lower() in text:
            collector += 1
    for kw in ANIME_IP_KEYWORDS:
        if kw.lower() in text:
            collector += 2
    if collector > 10:
        collector = 10
    if collector < 2:
        collector = 2

    # ---- 重要性评分 (1-10) ----
    importance = 3
    for kw in IMPORTANCE_HIGH_KEYWORDS:
        if kw.lower() in title_lower:
            importance += 3
        elif kw.lower() in text:
            importance += 1
    if importance > 10:
        importance = 10

    # ---- 分类提示 ----
    category_hint = _guess_category(text)

    # ---- 标签 ----
    tags = _extract_tags(text)

    # ---- 评分理由 ----
    reasons = []
    if urgency >= 7:
        reasons.append("含有限定/抽选/截止等时效性关键词")
    if collector >= 7:
        reasons.append("涉及热门 IP / 收藏品 / 手办周边")
    if importance >= 7:
        reasons.append("涉及重大 AI 公司、模型发布或政治事件")
    if importance < 5 and urgency < 5 and collector < 5:
        reasons.append("常规新闻，未见强信号")

    entry["importance_score"] = importance
    entry["urgency_score"] = urgency
    entry["collector_value"] = collector
    entry["category_hint"] = category_hint
    entry["tags"] = tags
    entry["reason_for_score"] = "；".join(reasons) if reasons else "常规评分"

    return entry


def _guess_category(text: str) -> Optional[str]:
    """根据文本猜测分类。"""
    text_lower = text.lower()

    # 动漫联动
    anime_collab_kw = ["collaboration", "collab", "联名", "联动", "合作", "tie-up", "cross-over", "crossover"]
    if any(kw in text_lower for kw in anime_collab_kw):
        return "anime_collab"

    # 周边/商品
    merch_kw = ["figure", "手办", "merchandise", "周边", "goods", "限定", "lottery", "抽选", "一番赏", "nendoroid"]
    if any(kw in text_lower for kw in merch_kw):
        return "merch_release"

    # 声优/漫画家
    seiyuu_kw = ["seiyuu", "声优", "voice actor", "voice actress", "manga artist", "漫画家", "autograph", "签售", "stage play", "舞台"]
    if any(kw in text_lower for kw in seiyuu_kw):
        return "seiyuu_manga_events"

    # AI / 科技
    tech_kw = ["ai", "artificial intelligence", "model", "模型", "llm", "gpt", "芯片", "chip", "nvidia", "openai", "deepseek", "open source", "开源"]
    if any(kw in text_lower for kw in tech_kw):
        return "ai_tech"

    # 政治
    politics_kw = ["election", "选举", "war", "战争", "sanctions", "制裁", "government", "政府", "president", "总统", "policy", "政策", "diplomacy", "外交"]
    if any(kw in text_lower for kw in politics_kw):
        return "politics_world"

    return None


def _extract_tags(text: str) -> list[str]:
    """提取关键词标签。"""
    text_lower = text.lower()
    tags: list[str] = []

    tag_map = {
        "AI": ["ai", "artificial intelligence", "machine learning", "deep learning"],
        "Anime": ["anime", "アニメ"],
        "Manga": ["manga", "漫画"],
        "Seiyuu": ["seiyuu", "声优", "voice actor"],
        "Figures": ["figure", "手办", "nendoroid"],
        "Limited": ["limited", "限定", "限量"],
        "OpenAI": ["openai"],
        "NVIDIA": ["nvidia"],
        "DeepSeek": ["deepseek"],
        "Google": ["google"],
        "Politics": ["election", "选举", "government", "政府", "president"],
        "War": ["war", "战争", "conflict"],
        "Economy": ["economy", "经济", "market", "市场"],
        "Japan": ["japan", "日本", "tokyo", "東京"],
        "China": ["china", "中国"],
        "Chip": ["chip", "芯片", "semiconductor"],
        "OpenSource": ["open source", "开源"],
        "Startup": ["startup", "创业"],
    }

    text_set = set(text_lower.split())
    for tag, keywords in tag_map.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)

    return list(dict.fromkeys(tags))  # 去重保序


def score_all(entries: list[dict]) -> list[dict]:
    """批量评分。"""
    return [score_entry(e) for e in entries]


def select_frontpage(entries: list[dict], count: int = 8) -> list[dict]:
    """选出头版新闻：综合得分最高的 N 条。"""
    scored = sorted(
        entries,
        key=lambda e: (
            e.get("importance_score", 0) * 3
            + e.get("urgency_score", 0) * 2
            + e.get("collector_value", 0)
        ),
        reverse=True,
    )
    return scored[:count]

# ---------------------------------------------------------------------------
# v3.0 新增：freshness 标签 & 头版排名
# ---------------------------------------------------------------------------
from datetime import datetime, timezone, timedelta

TZ_PERTH = timezone(timedelta(hours=8))


def add_freshness(entries: list[dict]) -> list[dict]:
    """为每条新闻添加 freshness 标签字段。"""
    now = datetime.now(TZ_PERTH)
    for e in entries:
        pub_str = e.get("published", "")
        e["is_recent"] = False
        e["is_old_context"] = False
        e["freshness_label"] = "时间未知"
        if pub_str:
            try:
                for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                    try:
                        pub_dt = datetime.strptime(pub_str, fmt).replace(tzinfo=TZ_PERTH)
                        break
                    except ValueError:
                        continue
                else:
                    continue
                hours = (now - pub_dt).total_seconds() / 3600
                if hours <= 24:
                    e["is_recent"] = True
                    e["freshness_label"] = "今日新情报"
                elif hours > 72:
                    e["is_old_context"] = True
                    e["freshness_label"] = "旧闻/背景信息"
                else:
                    e["freshness_label"] = f"{int(hours)}小时前"
            except Exception:
                pass
    return entries


def select_frontpage_ranked(entries: list[dict], count: int = 8) -> list[dict]:
    """选出头版新闻并标注排名。"""
    scored = sorted(
        entries,
        key=lambda e: (
            e.get("importance_score", 0) * 3
            + e.get("urgency_score", 0) * 2
            + e.get("collector_value", 0)
        ),
        reverse=True,
    )
    result = scored[:count]
    for i, item in enumerate(result):
        item["frontpage_rank"] = i + 1
    return result

# ---------------------------------------------------------------------------
# v4.0: 动漫活动字段检测
# ---------------------------------------------------------------------------
ANIME_EVENT_KEYWORDS = {
    "event_type": {
        "manga_signing": ["サイン会", "签名会", "署名会", "签售会", "signing event", "autograph session", "お渡し会", "私物サイン会"],
        "seiyuu_event": ["声優", "声优", "voice actor", "seiyuu", "キャスト", "见面会", "fan event", "meet and greet", "ツーショット撮影会", "トークショー", "talk show", "舞台挨拶", "stage greeting"],
        "merch_release": ["新周边", "限定", "limited", "发售", "release", "一番赏", "一番くじ", "ichiban kuji", "手办", "figure", "グッズ", "goods", "merchandise"],
        "lottery_sale": ["抽選", "抽选", "lottery", "当選", "当选"],
        "pop_up_store": ["pop-up", "pop up", "popup", "期间限定", "期間限定", "ポップアップ"],
        "collaboration": ["联名", "聯名", "collab", "联动", "コラボ", "tie-up"],
        "exhibition": ["展览", "展覧", "exhibition", "展示会", "原画展"],
    },
    "ticket_keywords": {
        "抽选": ["抽選", "抽选", "lottery"],
        "先着": ["先着", "first come", "先到先得"],
        "预约": ["予約", "预约", "reservation", "reserve"],
        "整理券": ["整理券", "numbered ticket"],
        "购买对象商品": ["対象商品", "对象商品", "购买特典", "購入特典"],
    },
    "date_keywords": ["開催日時", "開催日", "日時", "日程", "期間", "応募期間", "申込期間", "event date", "date", "when"],
    "venue_keywords": ["会場", "場所", "venue", "location", "開催場所", "東京都", "大阪", "名古屋", "福岡", "札幌", "渋谷", "秋葉原", "池袋", "新宿"],
    "person_keywords": ["先生", "老師", "漫画家", "manga artist", "作者", "author", "illustrator", "イラストレーター", "声優", "seiyuu", "voice actor"],
    "ip_keywords": ["鬼滅", "呪術", "SPY×FAMILY", "葬送のフリーレン", "チェンソーマン", "推しの子", "ダンダダン", "ONE PIECE", "ワンピース", "EVA", "エヴァ", "Fate", "hololive", "ホロライブ", "初音ミク", "ガンダム", "GUNDAM", "ポケモン", "Pokémon", "原神", "Genshin"],
}

def detect_anime_event_fields(entry: dict) -> dict | None:
    """从标题+摘要中检测动漫活动结构化字段。"""
    text = (entry.get("title","") + " " + entry.get("summary","") + " " + entry.get("body","")).lower()
    title = entry.get("title","")
    # Check if it's anime-related at all
    is_anime = any(kw.lower() in text for kws in ANIME_EVENT_KEYWORDS["event_type"].values() for kw in kws)
    is_anime = is_anime or any(kw.lower() in text for kw in ANIME_EVENT_KEYWORDS["ip_keywords"])
    if not is_anime:
        return None

    result = {
        "event_type": "unknown", "ip_or_work_title": "未知", "person_name": "未知",
        "role": "未知", "event_date": "未知", "event_time": "未知", "venue": "未知",
        "city": "未知", "country": "日本", "ticket_method": "未说明",
        "application_period": "未知", "lottery_or_first_come": "未知",
        "purchase_requirement": "未知", "goods_or_bonus": "未知",
        "official_source": entry.get("link",""), "urgency_level": "medium",
        "collector_value": entry.get("collector_value", 5),
        "travel_feasibility": "信息不足无法判断", "action_needed_cn": "查看原文获取详细信息",
    }

    # Detect event_type
    for etype, kws in ANIME_EVENT_KEYWORDS["event_type"].items():
        if any(kw.lower() in text for kw in kws):
            result["event_type"] = etype; break

    # Detect IP
    for ip in ANIME_EVENT_KEYWORDS["ip_keywords"]:
        if ip.lower() in text:
            result["ip_or_work_title"] = ip; break

    # Detect person
    for pk in ANIME_EVENT_KEYWORDS["person_keywords"]:
        if pk.lower() in text:
            result["person_name"] = f"包含: {pk}"; break

    # Detect ticket
    for method, kws in ANIME_EVENT_KEYWORDS["ticket_keywords"].items():
        if any(kw.lower() in text for kw in kws):
            result["ticket_method"] = method
            if not result.get("lottery_or_first_come") or result["lottery_or_first_come"] == "未知":
                result["lottery_or_first_come"] = method
            break

    # Urgency
    urgent_kws = ["抽選", "抽选", "先着", "今日", "明日", "本日", "截止", "締切", "deadline", "限定", "limited", "最后", "最後"]
    if any(kw.lower() in text for kw in urgent_kws):
        result["urgency_level"] = "high"
    result["urgency_level"] = "high" if any(kw.lower() in text for kw in ["抽選","抽选","先着","截止","締切"]) else result["urgency_level"]

    # Venue
    for vk in ANIME_EVENT_KEYWORDS["venue_keywords"]:
        if vk.lower() in text:
            if result["venue"] == "未知": result["venue"] = vk
            elif vk not in result["venue"]: result["venue"] += f" / {vk}"

    # Action
    if result["ticket_method"] == "抽选":
        result["action_needed_cn"] = "确认応募期間和当選通知日期，可能需要日本手机号或会员账号"
    elif result["ticket_method"] == "先着":
        result["action_needed_cn"] = "先到先得，建议尽早访问官方售票页面"
    elif result["ticket_method"] == "预约":
        result["action_needed_cn"] = "查看是否需要提前预约，确认预约开放时间"

    return result
