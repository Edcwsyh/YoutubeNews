import argparse
import json
import logging
import subprocess
import sys
import os
import shutil
import yt_dlp
from datetime import datetime


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "archive")
LOG_FILE = os.path.join(os.path.dirname(__file__), "pipeline.log")


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


def is_channel_url(url):
    """判断是否为频道URL"""
    return any(pattern in url for pattern in ["/@", "/channel/", "/user/", "/c/"])


def resolve_channel_to_latest_video(channel_url, logger=None):
    """解析频道URL，获取最新视频的URL"""
    if logger is None:
        logger = logging.getLogger(__name__)
    logger.info(f"解析频道获取最新视频: {channel_url}")

    # 统一转为 /videos 标签页
    if "/@" in channel_url and not channel_url.endswith("/videos"):
        if channel_url.endswith("/"):
            channel_url = channel_url.rstrip("/")
        channel_url = f"{channel_url}/videos"
    elif "/channel/" in channel_url or "/user/" in channel_url or "/c/" in channel_url:
        if not channel_url.endswith("/videos"):
            channel_url = channel_url.rstrip("/") + "/videos"

    logger.info(f"使用视频列表页: {channel_url}")

    ydl_opts = {
        "quiet": True,
        "simulate": True,
        "extract_flat": True,
        "flat_playlist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    videos = info.get("entries", [])
    if not videos:
        raise RuntimeError(f"未能从频道获取视频列表: {channel_url}")
    latest = videos[0]
    video_id = latest.get("id")
    video_title = latest.get("title")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"获取到最新视频: {video_title} ({video_url})")
    return video_url


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


def main():
    parser = argparse.ArgumentParser(description="完整流水线：下载转写 -> AI分析 -> Telegram推送 -> 归档")
    parser.add_argument("url", nargs="?", help="YouTube视频/频道URL（不传则读取配置文件）")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="工作目录")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过转写，直接用现有transcript.txt")
    parser.add_argument("--skip-archive", action="store_true", help="跳过归档")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="日志级别")
    args = parser.parse_args()

    logger = setup_logging(getattr(logging, args.log_level))

    logger.info("=" * 50)
    logger.info("流水线启动")
    logger.info(f"参数: url={args.url}, model={args.model}, work_dir={args.work_dir}, "
                f"skip_transcribe={args.skip_transcribe}, skip_archive={args.skip_archive}")

    config = load_config()
    url = args.url or config.get("youtube_channel_url")
    if not url or url == "https://www.youtube.com/@channel_name":
        logger.error("未提供YouTube URL，且config.json中未配置youtube_channel_url")
        sys.exit(1)

    logger.info(f"使用URL: {url}")

    # 如果是频道URL，解析获取最新视频URL
    if is_channel_url(url):
        logger.info("检测到频道URL，正在解析最新视频...")
        url = resolve_channel_to_latest_video(url, logger=logger)
        logger.info(f"将使用视频URL: {url}")

    base_dir = "/home/Edcwsyh/work"
    transcript_file = os.path.join(base_dir, "transcript.txt")
    analysis_file = os.path.join(base_dir, "analysis_result.txt")

    if not args.skip_transcribe:
        logger.info("=== 步骤1: 下载音频并转写 ===")
        run_cmd([
            sys.executable, "youtube_transcribe.py", url,
            "--model", args.model,
            "--output", transcript_file,
            "--work-dir", args.work_dir
        ], cwd=base_dir, logger=logger)

    if not os.path.exists(transcript_file):
        logger.error(f"未找到转写文件: {transcript_file}")
        sys.exit(1)
    logger.info(f"转写文件已就绪: {transcript_file} ({os.path.getsize(transcript_file)} bytes)")

    logger.info("=== 步骤2: AI分析生成报告 ===")
    run_cmd([sys.executable, "run_analysis.py"], cwd=base_dir, logger=logger)

    if not os.path.exists(analysis_file):
        logger.error(f"未生成分析报告: {analysis_file}")
        sys.exit(1)
    logger.info(f"分析报告已生成: {analysis_file} ({os.path.getsize(analysis_file)} bytes)")

    logger.info("=== 步骤3: 推送到Telegram ===")
    run_cmd([sys.executable, "telegram_push.py", analysis_file], cwd=base_dir, logger=logger)

    if not args.skip_archive:
        logger.info("=== 步骤4: 归档文件 ===")
        archive_files(base_dir, transcript_file, analysis_file, logger=logger)

    logger.info("=== 流水线完成 ===")


if __name__ == "__main__":
    main()