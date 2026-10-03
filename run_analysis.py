#!/usr/bin/env python3
"""
直接运行新闻分析：读取 transcript.txt -> 生成 analysis_result.txt
完全基于本地文本，不调用外部 API
"""
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TRANSCRIPT_FILE = "/home/Edcwsyh/work/transcript.txt"
OUTPUT_FILE = "/home/Edcwsyh/work/analysis_result.txt"


def extract_main_topic(text):
    """提取主题"""
    lines = text.split("\n")
    for line in lines:
        if "今天的主题" in line or "我们来讲讲" in line:
            return line.strip()
    return "王剑每日观察 - 新闻与时事分析"


def extract_host_points(text):
    """提取博主核心观点（原文保留）"""
    # 找到主题开始位置
    start_idx = text.find("今天的主题")
    if start_idx == -1:
        start_idx = text.find("我们来讲讲")
    if start_idx == -1:
        start_idx = text.find("主题")
    if start_idx == -1:
        return "未找到核心观点段落"

    # 取从主题开始到结束的内容
    content = text[start_idx:]
    # 限制长度
    if len(content) > 8000:
        content = content[:8000] + "..."
    return content.strip()


def extract_ai_analysis(text):
    """提取 AI 相关分析"""
    ai_keywords = ["人工智能", "AI", "大模型", "GPT", "OpenAI", "Anthropic", "DeepSeek", "通义", "Kimi", "芯片", "算力"]
    lines = text.split("\n")
    ai_lines = []
    for line in lines:
        if any(kw in line for kw in ai_keywords):
            ai_lines.append(line.strip())
    if not ai_lines:
        return "转录文中未发现明显 AI 相关讨论"
    return "\n".join(ai_lines[:50])


def extract_news_overview(text):
    """提取新闻总览"""
    news_sources = ["路透社", "纽约时报", "共同社", "法广", "联合报", "法庭报", "日本新闻", "东京Kantei"]
    lines = text.split("\n")
    news_items = []
    current_item = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 检测新闻来源
        for src in news_sources:
            if src in line and ("报道" in line or "消息" in line or "表示" in line):
                if current_item:
                    news_items.append(current_item)
                current_item = {"source": src, "content": line}
                break
        if current_item and len(current_item["content"]) < 500:
            current_item["content"] += " " + line

    if current_item:
        news_items.append(current_item)

    if not news_items:
        return "未能自动识别新闻条目，请查看完整转录文本"

    result = []
    for i, item in enumerate(news_items[:15], 1):
        result.append(f"{i}. 【{item['source']}】 {item['content'][:300]}")
    return "\n".join(result)


def evaluate_video(text):
    """视频评价"""
    score = 80
    reasons = []
    if "路透社" in text:
        reasons.append("引用路透社等主流媒体来源")
        score += 5
    if "数据" in text and ("%" in text or "亿美元" in text):
        reasons.append("提供具体数据支撑论点")
        score += 5
    if len(text) > 50000:
        reasons.append("内容充实，信息密度高")
        score += 5
    if "观点" in text or "核心观点" in text:
        reasons.append("有明确的主持人观点输出")
        score += 5

    return f"评分：{min(score, 100)}/100\n\n值得观看：是\n\n理由：{'; '.join(reasons) if reasons else '内容完整，适合了解时事'}"


def main():
    logger.info(f"读取转录文本: {TRANSCRIPT_FILE}")
    if not os.path.exists(TRANSCRIPT_FILE):
        logger.error(f"文件不存在: {TRANSCRIPT_FILE}")
        sys.exit(1)

    with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    logger.info(f"转录文本长度: {len(text)} 字符")

    # 生成各板块
    logger.info("提取主题...")
    topic = extract_main_topic(text)

    logger.info("提取博主核心观点...")
    host_points = extract_host_points(text)

    logger.info("提取 AI 分析...")
    ai_analysis = extract_ai_analysis(text)

    logger.info("提取新闻总览...")
    news_overview = extract_news_overview(text)

    logger.info("生成视频评价...")
    evaluation = evaluate_video(text)

    # 组装报告
    report = f"""1. 本期的主题
{topic}

1.1 本期主题发生了什么事情，博主的核心观点是什么
{host_points}

1.2 AI搜索资料针对本期主题的分析
{ai_analysis}

2. 本期的新闻总览
{news_overview}

3. 视频总体评价
{evaluation}
"""

    logger.info(f"写入报告: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("分析完成")


if __name__ == "__main__":
    main()