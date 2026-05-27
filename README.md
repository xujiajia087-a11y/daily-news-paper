# 📰 JiaJia Daily 情报日报 5.0 — Interactive Website Edition

AI 主编自动整理的中文情报日报网站。
= 动漫/周边/签售追踪 + AI/科技/政治解读 + 美股影响分析 + 交互式网站

## 🚀 架构

```
Python 数据生成层         前端网站层 (static SPA)
main.py                  site/index.html
  ↓ RSS fetch            site/assets/app.js
  ↓ DeepSeek AI          site/assets/style.css
  ↓ JSON output          site/data/daily-news.json
  ↓                      site/data/watchlist.json
site/data/*.json  ←──→  fetch + render
```

## 🔄 数据如何更新？（重要！）

> ⚠️ **刷新浏览器不会获取新数据。** 数据由 GitHub Actions 自动抓取，每天一次。

```
你的浏览器打开网站
    └── fetch site/data/daily-news.json
            └── 这个 JSON 是上次 GitHub Actions 生成的
                    └── 只有 Actions 再次跑完才会更新
```

**更新流程：**

1. GitHub Actions 每天 **Perth 09:00 (UTC 01:00)** 自动触发
2. 抓取 RSS → AI 分析 → 生成 `site/data/*.json`
3. 自动部署到 GitHub Pages
4. 用户下次打开网页时看到最新数据（浏览器会自动拉取新 JSON，因为有 cache busting）

**如何立即更新（手动触发）：**

1. 打开 [Actions 页面](https://github.com/xujiajia087-a11y/daily-news-paper/actions)
2. 左侧选 **Daily News Paper v5**
3. 点 **Run workflow** → 绿色的 **Run workflow** 按钮
4. 等待 5-10 分钟，刷新网站即可看到最新数据

**我的网站不自动更新怎么办？**

- 检查 GitHub Actions 最近一次运行是否成功
- 确认 `DEEPSEEK_API_KEY` 在 Settings → Secrets 里没过期
- 手动 Run workflow 一次看日志定位问题

## 🖥️ 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxx

# 3. 生成数据
python main.py

# 4. 启动本地网站
cd site
python3 -m http.server 8080 --bind 127.0.0.1

# 5. 浏览器打开
open http://127.0.0.1:8080/
```

> 💡 本地预览必须通过 HTTP server，不能直接打开 `file:///` 路径（JSON 会被浏览器拦截）。

## 🌐 部署到 GitHub Pages

### 第一步：创建 GitHub 仓库

在 GitHub 上创建一个**公开仓库**，例如 `daily-news-paper`。

> 仓库名决定 Pages URL：`https://<你的用户名>.github.io/daily-news-paper/`

```bash
cd /Users/xujiajia/Documents/skill/daily-news-paper
git remote add origin https://github.com/<你的用户名>/daily-news-paper.git
git add -A
git commit -m "Initial commit: JiaJia Daily 5.0"
git push -u origin main
```

### 第二步：设置 GitHub Secrets

1. 打开仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. Name: `DEEPSEEK_API_KEY`
4. Value: 你的 DeepSeek API Key（以 `sk-` 开头）
5. 点击 **Add secret**

### 第三步：启用 GitHub Pages

1. 打开仓库 → **Settings** → **Pages**
2. **Source** 选择 **GitHub Actions**
3. 保存

### 第四步：首次运行

1. 打开仓库 → **Actions** 标签
2. 左侧找到 **Daily News Paper v5**
3. 点击 **Run workflow** → **Run workflow**
4. 等待约 5-10 分钟（抓取 + AI 分析需要时间）
5. 部署成功后，访问：`https://<你的用户名>.github.io/daily-news-paper/`

### 之后每天自动运行

Workflow 已配置 `schedule: 0 1 * * *`（UTC 01:00 = Perth 09:00），每天自动抓取最新新闻并更新网站。

### 手动运行

在 Actions 标签页选择 workflow → **Run workflow**，支持两个选项：
- 默认运行（生成数据 + 部署）
- 勾选 `skip_commit` 跳过 commit 数据文件（仅部署 Pages）

## 🌏 中国朋友访问

- GitHub Pages 是公网服务，中国大陆访问**可能不稳定**
- 如需更稳定，可考虑：
  - **Cloudflare Pages**（速度较好，无需备案）— 导入 GitHub 仓库即可
  - **Vercel**（类似，自动部署）
  - 腾讯云 COS 静态网站 / 阿里云 OSS（需备案 + 自定义域名）
- 使用中国内地云资源 + 自定义域名通常需要 **ICP 备案**

## 🔍 网站交互功能

| 功能 | 说明 |
|---|---|
| **30秒看懂今天** | 核心判断、值得蹲的动漫信息、美股影响、噪音过滤 |
| **影响地图** | 6 方向影响卡片，点击筛选对应新闻 |
| **搜索** | 标题 / 摘要 / 来源 / 标签 / 人物 / IP / 地点 |
| **分类 Tab** | 全部 / 动漫 / 美股 / AI科技 / 政治 |
| **快捷 Chips** | 高重要 / 高紧急 / 需行动 / 美股 / 动漫 / 抽选 / 今日 |
| **排序** | 重要性 / 紧急度 / 追踪价值 / 收藏价值 |
| **卡片展开** | 默认紧凑，点击展开完整分析 |
| **动漫 Timeline** | 日期、地点、票务、応募期間、游客友好度 |
| **美股面板** | 市场语气、指数影响、板块表、主题观察、风险因素 |
| **Watchlist** | 未来 7-30 天追踪事件表格 |

## 📁 项目结构

```
daily-news-paper/
├── main.py              # Python 数据生成器
├── feeds.yaml           # RSS 订阅源配置
├── article_fetcher.py   # 网页正文抓取
├── dedupe.py            # 去重
├── scorer.py            # 评分 + 动漫活动检测
├── summarizer.py        # DeepSeek AI 总结
├── site/                # 🌐 前端网站
│   ├── index.html       # 网站入口
│   ├── .nojekyll        # 禁用 Jekyll 处理
│   ├── assets/
│   │   ├── app.js       # 交互逻辑
│   │   └── style.css    # 网站样式
│   └── data/            # 数据文件（自动生成）
│       ├── daily-news.json
│       └── watchlist.json
├── output/              # 传统输出（legacy）
│   ├── daily-news.html
│   ├── daily-news.md
│   └── daily-news.json
├── .env.example         # API Key 配置示例
├── requirements.txt
└── .github/workflows/
    └── daily-news.yml   # 自动抓取 + Pages 部署
```

## ❓ 常见问题

### 为什么网页打开是空白的？

1. 确认已运行 `python main.py` 生成了 `site/data/daily-news.json`
2. 确认是用 HTTP server 打开的，不是 `file:///` 路径
3. 打开浏览器开发者工具 → Console，查看是否有报错

### GitHub Pages 部署后打不开？

1. 确认 `Settings → Pages → Source` 选的是 **GitHub Actions**
2. 确认 `DEEPSEEK_API_KEY` 已在 Actions Secrets 中正确配置
3. 查看 Actions 运行日志，确认所有步骤都通过
4. Pages URL 格式：`https://<用户名>.github.io/<仓库名>/`

### 为什么新闻少 / 动漫活动信息少？

- RSS 源有限，建议在 `feeds.yaml` 中添加更多源
- 动漫活动信息主要来自 PR TIMES、Animate Times 等日本源
- 可以添加 HTML 源（`source_type: html_list`）来抓取活动页面

### 为什么 DeepSeek 总结失败？

- 确认 `.env` 中 `DEEPSEEK_API_KEY` 正确
- DeepSeek API 有速率限制，大量新闻可能触发限流
- 检查 `summarizer.py` 中的超时设置

## ⚠️ 免责声明

- 美股影响分析仅用于**信息整理**，**不构成投资建议**
- 股票代码仅作为主题观察参考，不是买卖建议
- 新闻内容由 AI 整理，可能存在事实错误，请以原文为准
