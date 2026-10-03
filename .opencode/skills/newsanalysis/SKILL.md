---
name: newsanalysis
description: Analyze YouTube transcript from /home/Edcwsyh/work/transcript.txt and generate structured analysis report to /home/Edcwsyh/work/analysis_result.txt. Extract: 1) main topic, 2) topic with host's core points (verbatim), 3) AI search analysis on topic, 4) news overview with credibility, 5) video evaluation (score 100 + worth watching). Based entirely on local text, no external models or APIs.
---
# News Analysis Skill

## When to use me
Use this skill when the YouTube video transcript (`transcript.txt`) needs to be analyzed into the specified structured report. The analysis is based entirely on local text, with no external models, APIs, or Telegram involvement.

## What I do
1. Read the transcript from the default path `/home/Edcwsyh/work/transcript.txt`.
2. Extract the following sections **verbatim** and write to `/home/Edcwsyh/work/analysis_result.txt`:
   - **1. 本期的主题**: Summarize the main topic of the episode.
   - **1.1 本期主题发生了什么事情，博主的核心观点是什么**: Extract the host's core points directly from the transcript (original text preserved, no paraphrasing).
   - **1.2 AI搜索资料针对本期主题的分析**: Extract any AI-related search/discussion analysis from the transcript.
   - **2. 本期的新闻总览**: Identify major news items, summarize what happened, and assess credibility based on source labels (e.g., 路透社, 纽约时报).
   - **3. 视频总体评价**: Give a score out of 100 and state whether the video is worth watching, with a brief rationale.
3. Do not modify any other files. Do not call any external APIs, databases, or models. Do not generate any Telegram-related content or calls.

## Interaction with opencode
- opencode can load this skill by calling: `skill({ name: "newsanalysis" })`
- When loaded, the skill's body is injected into the current context.
- opencode will follow the instructions to read `transcript.txt` and write `analysis_result.txt`.
- If you wish to require manual approval before the skill runs, add in the frontmatter: `metadata: { opencode/autoinvoke: false }`.

## Paths are relative to the directory containing this SKILL.md file, but default paths are absolute as specified.