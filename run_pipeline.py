import argparse
import json
import subprocess
import sys
import os
import shutil
from datetime import datetime


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "archive")


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")
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


def archive_files(base_dir, transcript_file, analysis_file):
    """归档 transcript.txt 和 analysis_result.txt"""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    for src_file, base_name in [(transcript_file, "transcript"), (analysis_file, "analysis")]:
        if not os.path.exists(src_file):
            continue
        seq = get_next_sequence(ARCHIVE_DIR, base_name, date_str)
        ext = os.path.splitext(src_file)[1]
        dst_name = f"{base_name}_{date_str}_{seq}{ext}"
        dst_path = os.path.join(ARCHIVE_DIR, dst_name)
        shutil.copy2(src_file, dst_path)
        print(f"归档: {dst_name}")


def main():
    parser = argparse.ArgumentParser(description="完整流水线：下载转写 -> AI分析 -> Telegram推送 -> 归档")
    parser.add_argument("url", nargs="?", help="YouTube视频/频道URL（不传则读取配置文件）")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="工作目录")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过转写，直接用现有transcript.txt")
    parser.add_argument("--skip-archive", action="store_true", help="跳过归档")
    args = parser.parse_args()

    config = load_config()
    url = args.url or config.get("youtube_channel_url")
    if not url or url == "https://www.youtube.com/@channel_name":
        print("错误: 请提供YouTube URL或在config.json中配置youtube_channel_url")
        sys.exit(1)

    base_dir = "/home/Edcwsyh/work"
    transcript_file = os.path.join(base_dir, "transcript.txt")
    analysis_file = os.path.join(base_dir, "analysis_result.txt")

    if not args.skip_transcribe:
        print("=== 步骤1: 下载音频并转写 ===")
        run_cmd([
            sys.executable, "youtube_transcribe.py", url,
            "--model", args.model,
            "--output", transcript_file,
            "--work-dir", args.work_dir
        ], cwd=base_dir)

    if not os.path.exists(transcript_file):
        print(f"错误: 未找到 {transcript_file}")
        sys.exit(1)

    print("=== 步骤2: AI分析生成报告 ===")
    run_cmd([sys.executable, "-m", "opencode", "skill", "newsanalysis"], cwd=base_dir)

    if not os.path.exists(analysis_file):
        print(f"错误: 未生成 {analysis_file}")
        sys.exit(1)

    print("=== 步骤3: 推送到Telegram ===")
    run_cmd([sys.executable, "telegram_push.py", analysis_file], cwd=base_dir)

    if not args.skip_archive:
        print("=== 步骤4: 归档文件 ===")
        archive_files(base_dir, transcript_file, analysis_file)

    print("=== 流水线完成 ===")


if __name__ == "__main__":
    main()