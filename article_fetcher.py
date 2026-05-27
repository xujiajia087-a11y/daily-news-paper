#!/usr/bin/env python3
"""article_fetcher.py — 从 RSS 条目的链接抓取网页正文。

策略：
1. 先用 og:description / meta description
2. 再用 <article> / <main> / .content 等常见选择器提取正文
3. 失败则退回 RSS summary
"""

import re
import html as _html
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
TIMEOUT = 15
USER_AGENT = "daily-news-paper/2.0 (RSS Reader; +https://github.com)"
MAX_CHARS = 3000

# 常见正文选择器（按优先级）
CONTENT_SELECTORS = [
    "article",
    '[role="main"]',
    "main",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".content",
    ".post-body",
    "#article-body",
    ".story-body",
    '[itemprop="articleBody"]',
]


def _clean_html(raw: str) -> str:
    """去掉 HTML 标签，整理空白。"""
    soup = BeautifulSoup(raw, "lxml")
    text = soup.get_text(separator="\n")
    # 压缩连续空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _extract_body(html_text: str) -> Optional[str]:
    """从 HTML 中提取正文文本。"""
    soup = BeautifulSoup(html_text, "lxml")

    # 1. 尝试 og:description / meta description
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or "").lower()
        name = (meta.get("name") or "").lower()
        content = meta.get("content", "")
        if ("og:description" in prop or "description" in name) and len(content) > 60:
            return content.strip()

    # 2. 尝试内容选择器
    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = _clean_html(str(el))
            if len(text) > 100:
                return text

    # 3. 退回 body
    body = soup.find("body")
    if body:
        for tag in body.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = _clean_html(str(body))
        if len(text) > 100:
            return text

    return None


def fetch_article(url: str) -> str:
    """抓取网页正文，失败退回空字符串。

    Args:
        url: 文章链接

    Returns:
        正文文本，最多 MAX_CHARS 字符；失败返回空串
    """
    if not url:
        return ""

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()

        # 检测内容类型
        ct = resp.headers.get("Content-Type", "")
        if "text/html" not in ct and "application/xhtml" not in ct:
            return ""  # 非 HTML，跳过

        body = _extract_body(resp.text)
        if body and len(body) > 20:
            return body[:MAX_CHARS]

    except Exception:
        pass

    return ""


def enrich_entry(entry: dict, timeout: int = TIMEOUT, user_agent: str = USER_AGENT) -> dict:
    """为单条新闻条目抓取正文。

    Args:
        entry: 包含 'link' 和 'summary' 的条目

    Returns:
        添加了 'body' 字段的条目
    """
    global TIMEOUT, USER_AGENT
    TIMEOUT = timeout
    USER_AGENT = user_agent

    link = entry.get("link", "")
    body = fetch_article(link)
    if body:
        entry["body"] = body
        entry["body_source"] = "fetched"
    else:
        # 退回 RSS summary
        summary = entry.get("summary", "")
        if summary:
            soup = BeautifulSoup(summary, "lxml")
            text = soup.get_text(separator="\n").strip()
            entry["body"] = text[:MAX_CHARS]
        else:
            entry["body"] = ""
        entry["body_source"] = "rss_summary"

    return entry
