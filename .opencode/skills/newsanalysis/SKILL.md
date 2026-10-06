---
name: newsanalysis
description: Analyze YouTube transcript from /home/Edcwsyh/work/transcript.txt and generate structured analysis report to /home/Edcwsyh/work/analysis_result.md. Extract: 1) main topic, 2) topic with host's core points (verbatim), 3) AI search analysis on topic with commentary, 4) news overview with credibility & AI commentary, 5) video evaluation (score 100 + worth watching). Output must be well-formatted Markdown for human readability.
---
# News Analysis Skill

## When to use me
Use this skill when the YouTube video transcript (`transcript.txt`) needs to be analyzed into a structured, human-readable report. The analysis combines local text understanding with **web search for fact-checking and expanding**.

## What I do
1. Read the transcript from the default path `/home/Edcwsyh/work/transcript.txt`.
2. **Search the web** for related information to fact-check and expand on the transcript content.
3. Generate a well-formatted **Markdown** report to `/home/Edcwsyh/work/analysis_result.md` with these sections:

### 1. 本期的主题
**简明扼要**（1-2句话）概括本期视频的核心主题。

### 1.1 本期主题发生了什么事情，博主的核心观点是什么
- **原文提取**：逐字保留博主关于主题的核心论述（关键数据、逻辑链条、结论）
- **结构化呈现**：用要点分隔不同论点，避免大段文本
- **关键数据标记**：数字、百分比、金额等关键信息加粗或单独列出
- **引用格式**：原文用 `> ` 块引用，关键句加粗标记

### 1.2 AI搜索资料针对本期主题的分析
**必须联网搜索验证和拓展，不仅基于常识**：

**背景补充**（联网搜索）：
- 搜索相关历史背景、国际对比、官方数据来源
- 时间轴对比、制度化进程对比
- 权威机构报告、专家学术观点

**逻辑评论**（结合搜索结果）：
- **强项**：精准识别的核心机制、解释力强的论点
- **弱项/隐含假设**：预设前提、忽略变量、结构性矛盾
- **反驳视角**：主流学派/另类理论的不同解释，**引用来源**

**数据核查**（表格格式，**必须引用搜索来源**）：
| 博主论点 | 可信度 | 搜索来源/佐证数据 |
|---------|-------|-------------|

**趋势研判**（结合最新数据）：
- 短期（1-2年）
- 中期（3-5年）
- 关键变量

### 2. 本期的新闻总览
**每条新闻结构化输出，需联网搜索最新进展**：

```
### [序号] 新闻标题
**来源**：权威媒体名  
**可信度**：高/中/低 （基于来源权威性、是否一手报道、是否有佐证）  
**核心事实**：
- 发生了什么（1-2句）
- 关键数字/时间/地点/人物
**AI 评论**（结合最新搜索）：
- 💡 事件意义/潜在影响
- 💡 关联性：与本期主题或宏观趋势的联系
- 💡 疑点/待追踪：信息缺口、官方回应缺失、数据存疑处
```

### 3. 视频总体评价
- **评分**：X/100
- **值得观看**：是 / 否 / 部分
- **评价理由**（分点，各 1-2 句，含星级）：
  - 信息密度/数据支撑：★★★★☆
  - 观点独到性/逻辑自洽性：★★★★★
  - 来源可信度/引用规范：★★★☆☆
  - 表达清晰度/冗余程度：★★★★★
  - 明显偏见/局限性：列点说明
- **一句话总结**：适合谁看、看什么部分

## 格式规范（强制）
- **标题用 `##`**，子标题用 `###`
- **要点用 `-` 或 `1.`**，避免超过 3 行的连续段落
- **关键数字/专有名词** 用 `**加粗**`
- **引用原文** 用 `> ` 块引用
- **AI 评论** 以 `💡` 前缀区分
- **表格** 用 Markdown 表格语法，**必须包含来源链接**
- **分隔符** 用 `---`
- 总长度控制在 3000-5000 字，信息密度高于原文

## Search Requirements（强制）
- **每个核心论点至少搜索 1-2 次**验证
- **数据核查表必须包含来源 URL**
- **新闻评论必须基于最新搜索结果**
- **使用 `websearch` 工具**，搜索关键词要精准（实体名+年份+关键词）

## Output
**仅输出 Markdown 文件**，不发送任何文本消息。

## Interaction with opencode
- opencode loads this skill via `skill({ name: "newsanalysis" })`
- Follow instructions to read `transcript.txt`, **search web**, write `analysis_result.md`
- Can use websearch tool for fact-checking and expanding. No Telegram content.

## Paths
Default paths are absolute as specified above.