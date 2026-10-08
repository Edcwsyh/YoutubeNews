import argparse
import json
import logging
import sys
import os
import shutil
import secrets
import time
from datetime import datetime

# 直接导入模块函数
from youtube_transcribe import transcribe_video
from telegram_push import push_result
from youtube_channel import (
    get_video_metadata,
    is_processable_video,
    resolve_channel_to_latest_video,
    validate_content_type,
)

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
    """加载流水线状态（记录每个频道最后处理的视频ID）"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"channels": {}}


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


def is_channel_url(url):
    """判断是否为频道URL"""
    return any(pattern in url for pattern in ["/@", "/channel/", "/user/", "/c/"])


def archive_files(base_dir, transcript_file, analysis_file, logger=None):
    """归档 transcript.txt 和 analysis_result.md"""
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


def run_pipeline_once(url, args, logger, config, channel_config=None):
    """执行单次流水线"""
    logger.info("=" * 50)
    logger.info("流水线启动")
    logger.info(f"参数: url={url}, model={args.model}, work_dir={args.work_dir}, "
                f"skip_transcribe={args.skip_transcribe}, skip_archive={args.skip_archive}")

    # 如果是频道URL，解析获取最新视频URL
    content_type = "all"
    if channel_config:
        content_type = channel_config.get("content_type", "all")
    try:
        validate_content_type(content_type)
    except ValueError as e:
        logger.error(str(e))
        return False, None
    if is_channel_url(url):
        logger.info("检测到频道URL，正在解析最新视频...")
        try:
            url = resolve_channel_to_latest_video(url, logger=logger, content_type=content_type)
        except Exception as e:
            logger.error(f"解析频道失败: {e}")
            return False, None
        if url is None:
            logger.info("没有符合配置的可处理内容，跳过本次处理")
            return True, None
        logger.info(f"将使用视频URL: {url}")

    video_id = extract_video_id(url)
    if video_id:
        logger.info(f"视频ID: {video_id}")

    # 直接传入视频 URL 时也检查类型和回放是否已就绪；无法确认则不下载。
    if not args.skip_transcribe:
        metadata = get_video_metadata(url, logger=logger)
        if not is_processable_video(metadata, content_type):
            status = metadata["live_status"] if metadata else "unknown"
            logger.info(f"内容不符合配置或尚不可处理，跳过本次处理: live_status={status}")
            return False, video_id

    base_dir = "/home/Edcwsyh/work"
    transcript_file = os.path.join(base_dir, "transcript.txt")
    analysis_file = os.path.join(base_dir, "analysis_result.md")

    if not args.skip_transcribe:
        logger.info("=== 步骤1: 下载音频并转写 ===")
        # 清理工作目录
        if os.path.exists(args.work_dir):
            logger.info(f"清理工作目录: {args.work_dir}")
            shutil.rmtree(args.work_dir, ignore_errors=True)
        try:
            transcribe_video(
                url,
                model=args.model,
                output=transcript_file,
                work_dir=args.work_dir,
                segment_seconds=300,
                log_level=args.log_level,
                logger=logger
            )
        except Exception as e:
            logger.error(f"转写失败: {e}")
            return False, None

    if not os.path.exists(transcript_file):
        logger.error(f"未找到转写文件: {transcript_file}")
        return False, None
    logger.info(f"转写文件已就绪: {transcript_file} ({os.path.getsize(transcript_file)} bytes)")

    logger.info("=== 步骤2: AI分析生成报告 ===")
    # opencode skill 仍需通过 CLI 运行（无 Python API）
    import subprocess

    # 为本次分析固定 session，避免 --continue 意外接续其他任务的会话。
    session_id = "ses_" + "".join(
        secrets.choice("_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for _ in range(26)
    )

    def run_analysis(prompt):
        cmd = ["opencode", "run", "--session", session_id]
        cmd.append(prompt)
        result = subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True)
        return result

    def delete_analysis_session():
        try:
            result = subprocess.run(
                ["opencode", "session", "delete", session_id],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"已删除 OpenCode session: {session_id}")
            else:
                logger.warning(f"删除 OpenCode session 失败: {result.stderr.strip()}")
        except Exception as e:
            logger.warning(f"删除 OpenCode session 时发生异常: {e}")

    # 可配置重试次数，优先级：命令行 > config.json > 默认5
    max_retries = getattr(args, 'ai_max_retries', None) or config.get('ai_max_retries', 5)
    result = run_analysis("使用 newsanalysis skill 分析 transcript.txt 并生成 analysis_result.md")
    
    for attempt in range(max_retries):
        if result.returncode == 0:
            break
        logger.warning(f"AI分析失败 (尝试 {attempt+1}/{max_retries}): {result.stderr}")
        if attempt < max_retries - 1:
            logger.info("重试中... (继续本次分析会话)")
            result = run_analysis("继续执行分析")
        else:
            logger.error(f"AI分析重试 {max_retries} 次均失败")
            return False, video_id
    delete_analysis_session()
    logger.debug(result.stdout)

    if not os.path.exists(analysis_file):
        logger.error(f"未生成分析报告: {analysis_file}")
        return False, video_id
    logger.info(f"分析报告已生成: {analysis_file} ({os.path.getsize(analysis_file)} bytes)")

    logger.info("=== 步骤3: 推送到Telegram ===")
    try:
        push_result(analysis_file, log_level=args.log_level, logger=logger, config=config)
    except Exception as e:
        logger.error(f"推送失败: {e}")
        return False, video_id

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
    channels = config.get("youtube_channels", [])
    if not channels:
        logger.error("config.json 中未配置 youtube_channels")
        sys.exit(1)

    enabled_channels = [c for c in channels if c.get("enabled", True)]
    if not enabled_channels:
        logger.error("没有启用的频道")
        sys.exit(1)

    # 在任何下载/分析之前检查配置，不能把拼错的类型默认为 all。
    for channel in enabled_channels:
        try:
            validate_content_type(channel.get("content_type", "all"))
        except ValueError as e:
            logger.error(f"频道 {channel.get('name', channel['url'])} 配置错误: {e}")
            sys.exit(1)

    # 单次运行模式：遍历所有启用的频道
    if not args.monitor:
        all_success = True
        for channel in enabled_channels:
            channel_url = channel["url"]
            logger.info(f"处理频道: {channel.get('name', channel_url)}")
            success, _ = run_pipeline_once(channel_url, args, logger, config, channel_config=channel)
            all_success = all_success and success
        sys.exit(0 if all_success else 1)

    # 监听模式：遍历所有启用的频道
    logger.info("=" * 50)
    logger.info(f"启动监听模式: 检查间隔={args.interval}秒, 频道数={len(enabled_channels)}")
    logger.info("按 Ctrl+C 停止")

    state = load_state()
    channel_states = state.get("channels", {})

    try:
        while True:
            logger.info("-" * 50)
            logger.info("开始新一轮检查...")

            for channel in enabled_channels:
                channel_url = channel["url"]
                channel_name = channel.get("name", channel_url)
                logger.info(f"检查频道: {channel_name}")

                # 获取该频道的上次处理视频ID
                last_video_id = channel_states.get(channel_url)

                # 解析最新视频（带重试）
                check_url = None
                max_retries = 3
                retry_delay = 60  # 初始延迟 60 秒
                for attempt in range(max_retries):
                    try:
                        check_url = channel_url
                        if is_channel_url(check_url):
                            check_url = resolve_channel_to_latest_video(
                                check_url,
                                logger=logger,
                                content_type=channel.get("content_type", "all"),
                            )
                        break  # 成功跳出重试循环
                    except Exception as e:
                        logger.warning(f"解析视频失败 (尝试 {attempt+1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            logger.info(f"{retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                        else:
                            logger.error(f"重试 {max_retries} 次均失败，跳过频道: {channel_name}")
                            check_url = None

                if check_url is None:
                    logger.info(f"频道 {channel_name} 无可处理内容或解析失败，跳过")
                    continue

                current_video_id = extract_video_id(check_url)
                logger.info(f"频道 {channel_name} 最新视频ID: {current_video_id}, 上次处理: {last_video_id}")

                if current_video_id and current_video_id != last_video_id:
                    logger.info(f"检测到新视频: {current_video_id}")
                    success, new_video_id = run_pipeline_once(
                        check_url, args, logger, config, channel_config=channel,
                    )
                    if success and new_video_id:
                        channel_states[channel_url] = new_video_id
                        state["channels"] = channel_states
                        save_state(state)
                        logger.info(f"已更新频道 {channel_name} 状态: {new_video_id}")
                else:
                    logger.info(f"频道 {channel_name} 无新视频，跳过")

            logger.info(f"本轮检查完成，等待 {args.interval} 秒后下次检查...")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("收到中断信号，退出监听模式")
    except Exception as e:
        logger.exception(f"监听模式异常，继续下一轮: {e}")
        logger.info(f"等待 {args.interval} 秒后重试...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
