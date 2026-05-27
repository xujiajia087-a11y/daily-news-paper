#!/usr/bin/env python3
"""dedupe.py — 新闻去重模块

策略：
1. 按 URL 精确去重（同一链接视为同一篇）
2. 按标题相似度去重（Levenshtein 距离 / 最长公共子串）
3. 同一新闻多来源时，保留时效最新 + 来源更多的版本
"""

import re
from typing import Optional


def _normalize_title(title: str) -> str:
    """规范化标题用于比较。"""
    t = title.lower().strip()
    # 去掉常见来源后缀
    t = re.sub(r"\s*[-|–—]\s*(bbc news|reuters|ap|afp|cnn|techcrunch|arstechnica).*$", "", t)
    # 去掉多余空格
    t = re.sub(r"\s+", " ", t)
    return t


def _title_similarity(a: str, b: str) -> float:
    """计算两个标题的相似度 (0-1)。

    使用最长公共子序列比例 + 词重叠率。
    """
    a = _normalize_title(a)
    b = _normalize_title(b)

    if a == b:
        return 1.0

    # 最长公共子序列
    def lcs_len(s1: str, s2: str) -> int:
        m, n = len(s1), len(s2)
        if m == 0 or n == 0:
            return 0
        prev = [0] * (n + 1)
        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev = curr
        return prev[n]

    lcs = lcs_len(a, b)
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    lcs_ratio = lcs / max_len

    # 词重叠率
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return lcs_ratio
    jaccard = len(words_a & words_b) / len(words_a | words_b)

    return 0.6 * lcs_ratio + 0.4 * jaccard


def deduplicate(entries: list[dict], threshold: float = 0.75) -> tuple[list[dict], int]:
    """去重新闻条目。

    Args:
        entries: 条目列表，每个至少包含 'link' 和 'title'
        threshold: 标题相似度阈值（高于此值视为重复）

    Returns:
        (去重后的条目列表, 去除的重复数量)
    """
    if not entries:
        return [], 0

    # 阶段 1: URL 精确去重
    seen_urls: set[str] = set()
    url_deduped: list[dict] = []
    url_dup_count = 0
    for e in entries:
        url = e.get("link", "").strip().rstrip("/")
        if not url:
            url_deduped.append(e)
            continue
        if url in seen_urls:
            url_dup_count += 1
            continue
        seen_urls.add(url)
        url_deduped.append(e)

    # 阶段 2: 标题相似度去重
    result: list[dict] = []
    title_dup_count = 0
    for e in url_deduped:
        is_dup = False
        for existing in result:
            sim = _title_similarity(e.get("title", ""), existing.get("title", ""))
            if sim >= threshold:
                # 保留时效更新的（按发布时间）
                if (e.get("published", "") or "") > (existing.get("published", "") or ""):
                    existing.update({k: v for k, v in e.items() if k != "title"})
                title_dup_count += 1
                is_dup = True
                break
        if not is_dup:
            result.append(e)

    total_dupes = url_dup_count + title_dup_count
    return result, total_dupes
