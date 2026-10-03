import argparse
import json
import logging
import subprocess
import sys
import os
import shutil
import time
import yt_dlp
from datetime import datetime


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "archive")
LOG_FILE = os.path.join(os.path.dirname(__file__), "pipeline.log")
STATE_FILE = os.path.join(os.path.dirname(__file__), ".pipeline_state.json")


def setup_logging(level=logging.INFO):
    """配置日志：同时输出到控制台和文件"""
    log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )
    return logging.getLogger(__name__)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    """加载流水线状态（记录最后处理的视频ID）"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_video_id": None}


def save_state(state):
    """保存流水线状态"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.getLogger(__name__).warning(f"保存状态失败: {e}")


def extract_video_id(url):
    """从 YouTube URL 提取 video_id"""
    import re
    # watch?v=xxx 格式
    m = re.search(r"[?&]v=([^&]+)", url)
    if m:
        return m.group(1)
    # youtu.be/xxx 格式
    m = re.search(r"youtu\.be/([^?&]+)", url)
    if m:
        return m.group(1)
    return None


def extract_video_id(url):
    """从 YouTube URL 提取 video_id"""
    import re
    # watch?v=xxx 格式
    m = re.search(r"[?&]v=([^&]+)", url)
    if m:
        return m.group(1)
    # youtu.be/xxx 格式
    m = re.search(r"youtu\.be/([^?&]+)", url)
    if m:
        return m.group(1)
    return None


def is_live_stream(video_url, logger=None):
    """检查视频是否为正在直播的流（排除已结束的直播回放 VOD）"""
    if logger is None:
        logger = logging.getLogger(__name__)
    try:
        import subprocess
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--print", "%(live_status)s|%(concurrent_view_count)s|%(release_timestamp)s", video_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 3:
                live_status = parts[0].strip().lower()
                concurrent = parts[1].strip()
                release_ts = parts[2].strip()
                
                if live_status in ("is_live", "live"):
                    # 判断是正在直播还是已结束的直播回放
                    # 如果 release_timestamp 存在且在过去，说明是 VOD
                    # 如果 concurrent_view_count 是 NA，可能是普通视频
                    import time
                    try:
                        if release_ts and release_ts != "NA":
                            release_time = int(release_ts)
                            if release_time < time.time():
                                logger.debug(f"视频为已结束的直播回放 (release_timestamp 在过去): {video_url}")
                                return False
                    except ValueError:
                        pass
                    
                    # 如果 concurrent_view_count 是数字且较大，可能正在直播
                    # 但 VOD 也可能有观看人数，所以不能只靠这个
                    # 最稳妥：如果 release_timestamp 在未来，才是正在直播
                    try:
                        if release_ts and release_ts != "NA":
                            release_time = int(release_ts)
                            if release_time > time.time():
                                logger.warning(f"检测到正在直播的视频 (未来 release_timestamp)，跳过: {video_url}")
                                return True
                    except ValueError:
                        pass
                    
                    logger.debug(f"视频标记为 is_live 但无法确定是否正在直播，当作 VOD 处理: {video_url}")
                    return False
                logger.debug(f"视频直播状态: {live_status}")
    except Exception as e:
        logger.debug(f"检查直播状态失败: {e}")
    return False


def is_channel_url(url):
    """判断是否为频道URL"""
    return any(pattern in url for pattern in ["/@", "/channel/", "/user/", "/c/"])


def resolve_channel_to_latest_video(channel_url, logger=None, max_age_hours=12):
    """解析频道URL，获取最新视频的URL（用 RSS 极速获取，过滤最近 N 小时，排除 Shorts）"""
    if logger is None:
        logger = logging.getLogger(__name__)
    logger.info(f"解析频道获取最新视频: {channel_url}")

    import requests
    import xml.etree.ElementTree as ET
    from datetime import datetime, timezone, timedelta
    import re

    # 1. 从 handle URL 提取 channel ID
    if "/@" in channel_url:
        handle_url = channel_url.rstrip("/")
        logger.debug(f"获取频道页面: {handle_url}")
        resp = requests.get(handle_url, timeout=10)
        resp.raise_for_status()
        # 从页面提取 channel ID
        match = re.search(r'channel/(UC[0-9A-Za-z_-]{22})', resp.text)
        if not match:
            raise RuntimeError(f"无法从页面提取 channel ID: {handle_url}")
        channel_id = match.group(1)
        logger.info(f"解析到 Channel ID: {channel_id}")
    elif "/channel/" in channel_url:
        channel_id = channel_url.split("/channel/")[-1].split("/")[0]
    else:
        raise RuntimeError(f"不支持的频道 URL 格式: {channel_url}")

    # 2. 请求 RSS feed（主频道 feed，包含所有内容，后续过滤 Shorts）
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    logger.debug(f"请求 RSS: {rss_url}")
    resp = requests.get(rss_url, timeout=10)
    resp.raise_for_status()

    # 3. 解析 XML
    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

    # 4. 遍历 entry，找最近 max_age_hours 小时内的非 Shorts 视频
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    logger.debug(f"时间截止线: {cutoff.isoformat()}")

    for entry in root.findall("atom:entry", ns):
        video_id_elem = entry.find("yt:videoId", ns)
        title_elem = entry.find("atom:title", ns)
        published_elem = entry.find("atom:published", ns)
        link_elem = entry.find("atom:link", ns)

        if video_id_elem is None or title_elem is None:
            continue

        video_id = video_id_elem.text
        title = title_elem.text

        # 解析发布时间
        published_str = published_elem.text if published_elem is not None else None
        if published_str:
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                published = datetime.now(timezone.utc)
        else:
            published = datetime.now(timezone.utc)

        # 过滤 Shorts：检查链接或标题
        is_short = False
        if link_elem is not None:
            href = link_elem.get("href", "")
            if "/shorts/" in href:
                is_short = True
        if "#shorts" in title.lower() or "#shortsvideo" in title.lower():
            is_short = True

        logger.debug(f"候选: {title} ({video_id}) @ {published.isoformat()} short={is_short}")

        if is_short:
            continue

        if published >= cutoff:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"获取到最新视频 (最近 {max_age_hours}h): {title} ({video_url})")
            return video_url

    # 如果最近 N 小时没有视频，返回最新的非 Shorts 视频
    for entry in root.findall("atom:entry", ns):
        video_id_elem = entry.find("yt:videoId", ns)
        title_elem = entry.find("atom:title", ns)
        link_elem = entry.find("atom:link", ns)

        if video_id_elem is None or title_elem is None:
            continue

        video_id = video_id_elem.text
        title = title_elem.text

        is_short = False
        if link_elem is not None:
            href = link_elem.get("href", "")
            if "/shorts/" in href:
                is_short = True
        if "#shorts" in title.lower() or "#shortsvideo" in title.lower():
            is_short = True

        if not is_short:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.warning(f"最近 {max_age_hours}h 无新视频，回退到最新非Shorts: {title} ({video_url})")
            return video_url

    raise RuntimeError(f"RSS 中未找到任何非 Shorts 视频: {rss_url}")


def run_cmd(cmd, cwd=None, logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)
    cmd_str = " ".join(cmd)
    logger.info(f"RUN: {cmd_str}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            logger.debug(f"OUT: {line}")
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            logger.warning(f"ERR: {line}")
    if result.returncode != 0:
        logger.error(f"Command failed (exit={result.returncode}): {cmd_str}")
        raise RuntimeError(f"Command failed with exit code {result.returncode}")
    logger.info(f"OK: {cmd_str}")
    return result


def get_next_sequence(archive_dir, base_name, date_str):
    """获取当天的下一个序号"""
    max_seq = 0
    if not os.path.exists(archive_dir):
        return 1
    for fname in os.listdir(archive_dir):
        if fname.startswith(f"{base_name}_{date_str}_"):
            try:
                seq = int(fname.split("_")[-1].split(".")[0])
                max_seq = max(max_seq, seq)
            except ValueError:
                continue
    return max_seq + 1


def archive_files(base_dir, transcript_file, analysis_file, logger=None):
    """归档 transcript.txt 和 analysis_result.txt"""
    if logger is None:
        logger = logging.getLogger(__name__)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    for src_file, base_name in [(transcript_file, "transcript"), (analysis_file, "analysis")]:
        if not os.path.exists(src_file):
            logger.warning(f"源文件不存在，跳过归档: {src_file}")
            continue
        seq = get_next_sequence(ARCHIVE_DIR, base_name, date_str)
        ext = os.path.splitext(src_file)[1]
        dst_name = f"{base_name}_{date_str}_{seq}{ext}"
        dst_path = os.path.join(ARCHIVE_DIR, dst_name)
        shutil.copy2(src_file, dst_path)
        logger.info(f"归档: {dst_name} <- {src_file}")


def run_pipeline_once(url, args, logger, config):
    """执行单次流水线"""
    logger.info("=" * 50)
    logger.info("流水线启动")
    logger.info(f"参数: url={url}, model={args.model}, work_dir={args.work_dir}, "
                f"skip_transcribe={args.skip_transcribe}, skip_archive={args.skip_archive}")

    # 如果是频道URL，解析获取最新视频URL
    if is_channel_url(url):
        logger.info("检测到频道URL，正在解析最新视频...")
        url = resolve_channel_to_latest_video(url, logger=logger)
        logger.info(f"将使用视频URL: {url}")

    video_id = extract_video_id(url)
    if video_id:
        logger.info(f"视频ID: {video_id}")

    # 检查是否为正在直播
    if not args.skip_transcribe and is_live_stream(url, logger=logger):
        logger.info("检测到正在直播，跳过本次处理")
        return False, video_id

    base_dir = "/home/Edcwsyh/work"
    transcript_file = os.path.join(base_dir, "transcript.txt")
    analysis_file = os.path.join(base_dir, "analysis_result.txt")

    if not args.skip_transcribe:
        logger.info("=== 步骤1: 下载音频并转写 ===")
        # 清理工作目录
        if os.path.exists(args.work_dir):
            logger.info(f"清理工作目录: {args.work_dir}")
            shutil.rmtree(args.work_dir, ignore_errors=True)
        run_cmd([
            sys.executable, "youtube_transcribe.py", url,
            "--model", args.model,
            "--output", transcript_file,
            "--work-dir", args.work_dir
        ], cwd=base_dir, logger=logger)

    if not os.path.exists(transcript_file):
        logger.error(f"未找到转写文件: {transcript_file}")
        return False, None
    logger.info(f"转写文件已就绪: {transcript_file} ({os.path.getsize(transcript_file)} bytes)")

    logger.info("=== 步骤2: AI分析生成报告 ===")
    run_cmd([
        "opencode", "run",
        "使用 newsanalysis skill 分析 transcript.txt 并生成 analysis_result.txt"
    ], cwd=base_dir, logger=logger)

    if not os.path.exists(analysis_file):
        logger.error(f"未生成分析报告: {analysis_file}")
        return False, video_id
    logger.info(f"分析报告已生成: {analysis_file} ({os.path.getsize(analysis_file)} bytes)")

    logger.info("=== 步骤3: 推送到Telegram ===")
    run_cmd([sys.executable, "telegram_push.py", analysis_file], cwd=base_dir, logger=logger)

    if not args.skip_archive:
        logger.info("=== 步骤4: 归档文件 ===")
        archive_files(base_dir, transcript_file, analysis_file, logger=logger)

    logger.info("=== 流水线完成 ===")
    return True, video_id


def main():
    parser = argparse.ArgumentParser(description="完整流水线：下载转写 -> AI分析 -> Telegram推送 -> 归档")
    parser.add_argument("url", nargs="?", help="YouTube视频/频道URL（不传则读取配置文件）")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="工作目录")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过转写，直接用现有transcript.txt")
    parser.add_argument("--skip-archive", action="store_true", help="跳过归档")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="日志级别")
    parser.add_argument("--monitor", action="store_true", help="持续监听模式，定期检查新视频")
    parser.add_argument("--interval", type=int, default=300, help="监听模式下的检查间隔(秒，默认300)")
    args = parser.parse_args()

    logger = setup_logging(getattr(logging, args.log_level))

    config = load_config()
    url = args.url or config.get("youtube_channel_url")
    if not url or url == "https://www.youtube.com/@channel_name":
        logger.error("未提供YouTube URL，且config.json中未配置youtube_channel_url")
        sys.exit(1)

    # 单次运行模式
    if not args.monitor:
        success, _ = run_pipeline_once(url, args, logger, config)
        sys.exit(0 if success else 1)

    # 监听模式
    logger.info("=" * 50)
    logger.info(f"启动监听模式: 检查间隔={args.interval}秒, URL={url}")
    logger.info("按 Ctrl+C 停止")

    state = load_state()
    last_video_id = state.get("last_video_id")

    try:
        while True:
            logger.info("-" * 50)
            logger.info("检查新视频...")

            # 解析最新视频
            check_url = url
            if is_channel_url(check_url):
                check_url = resolve_channel_to_latest_video(check_url, logger=logger)

            current_video_id = extract_video_id(check_url)
            logger.info(f"最新视频ID: {current_video_id}, 上次处理: {last_video_id}")

            if current_video_id and current_video_id != last_video_id:
                logger.info(f"检测到新视频: {current_video_id}")
                success, new_video_id = run_pipeline_once(check_url, args, logger, config)
                if success and new_video_id:
                    last_video_id = new_video_id
                    state["last_video_id"] = last_video_id
                    save_state(state)
                    logger.info(f"已更新状态: last_video_id={last_video_id}")
            else:
                logger.info("无新视频，跳过")

            logger.info(f"等待 {args.interval} 秒后下次检查...")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("收到中断信号，退出监听模式")
    except Exception as e:
        logger.error(f"监听模式异常: {e}")
        raise


if __name__ == "__main__":
    main()