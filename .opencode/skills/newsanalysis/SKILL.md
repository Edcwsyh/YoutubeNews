---
name: newsanalysis
description: Analyze YouTube transcript from /home/Edcwsyh/work/transcript.txt and generate structured analysis report to /home/Edcwsyh/work/analysis_result.txt. Extract: 1) main topic, 2) topic with host's core points (verbatim), 3) AI search analysis on topic with commentary, 4) news overview with credibility & AI commentary, 5) video evaluation (score 100 + worth watching). Output must be well-formatted for human readability.
---
# News Analysis Skill

## When to use me
Use this skill when the YouTube video transcript (`transcript.txt`) needs to be analyzed into a structured, human-readable report. The analysis is based entirely on local text, with no external models, APIs, or Telegram involvement.

## What I do
1. Read the transcript from the default path `/home/Edcwsyh/work/transcript.txt`.
2. Generate a well-formatted report to `/home/Edcwsyh/work/analysis_result.txt` with these sections:

### 1. 本期的主题
**简明扼要**（1-2句话）概括本期视频的核心主题。

### 1.1 本期主题发生了什么事情，博主的核心观点是什么
- **原文提取**：逐字保留博主关于主题的核心论述（关键数据、逻辑链条、结论）
- **结构化呈现**：用要点分隔不同论点，避免大段文本
- **关键数据标记**：数字、百分比、金额等关键信息加粗或单独列出

### 1.2 AI搜索资料针对本期主题的分析
**不仅总结，还要评论**：
- **背景补充**：基于常识补充博主未提及的关键背景（历史对比、国际经验、数据来源）
- **逻辑评论**：点出论证中的强项/弱项、隐含假设、可能的反驳视角
- **数据核查**：标注博主引用数据的来源可信度，补充同期对比数据
- **趋势研判**：基于主题给出短期/中期走势判断（如有数据支撑）
- **格式**：分点陈述，每点 1-3 句，避免长段落

### 2. 本期的新闻总览
**每条新闻结构化输出**：
```
## [序号] 新闻标题
**来源**：路透社 / 纽约时报 / 共同社 等
**可信度**：高 / 中 / 低 （基于来源权威性、是否一手报道、是否有佐证）
**核心事实**：
- 发生了什么（1-2句）
- 关键数字/时间/地点/人物
**AI 评论**：
- 事件意义/潜在影响
- 关联性：与本期主题或宏观趋势的联系
- 疑点/待追踪：信息缺口、官方回应缺失、数据存疑处
```

### 3. 视频总体评价
- **评分**：X/100
- **值得观看**：是 / 否 / 部分
- **评价理由**（分点，各 1-2 句）：
  - 信息密度/数据支撑
  - 观点独到性/逻辑自洽性
  - 来源可信度/引用规范
  - 表达清晰度/冗余程度
  - 明显偏见/局限性
- **一句话总结**：适合谁看、看什么部分

## 格式规范（强制）
- **标题用 `##`**，子标题用 `###`
- **要点用 `-` 或 `1.`**，避免超过 3 行的连续段落
- **关键数字/专有名词** 用 `**加粗**`
- **引用原文** 用 `> ` 块引用
- **AI 评论** 以 `💡` 或 `【AI 评论】` 前缀区分
- 总长度控制在 3000-5000 字，信息密度高于原文

## Interaction with opencode
- opencode loads this skill via `skill({ name: "newsanalysis" })`
- Follow instructions to read `transcript.txt` and write `analysis_result.txt`
- No external APIs, databases, or models. No Telegram content.

## Paths
Default paths are absolute as specified above.