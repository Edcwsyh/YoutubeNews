import argparse
import json
import os
import sys
import time

import yt_dlp
from faster_whisper import WhisperModel


STATE_FILE = "/tmp/yt_monitor_state.json"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_video_id": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_channel_videos(url, max_results=5):
    ydl_opts = {
        "quiet": True,
        "simulate": True,
        "extract_flat": True,
        "flat_playlist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    videos = info.get("entries", [])
    result = []
    for v in videos[:max_results]:
        result.append({
            "id": v.get("id"),
            "title": v.get("title"),
            "url": f"https://www.youtube.com/watch?v={v.get('id')}",
        })
    return result


def download_and_transcribe(url, model="base", work_dir="/tmp/yt_transcribe"):
    audio_file = download_audio(url, work_dir)
    segment_files = split_audio(audio_file, work_dir, segment_seconds=300)
    transcribe_segments(segment_files, model, f"{work_dir}/transcript.txt")


def download_audio(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": os.path.join(output_dir, "audio.%(ext)s"),
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    audio_file = ydl.prepare_filename(info)
    if not os.path.exists(audio_file):
        audio_files = __import__("glob").glob(os.path.join(output_dir, "audio.*"))
        if not audio_files:
            raise FileNotFoundError("Audio file not found")
        audio_file = audio_files[0]
    return audio_file


def split_audio(audio_file, output_dir, segment_seconds=300):
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "seg_%03d.webm")
    subprocess = __import__("subprocess")
    subprocess.run(
        ["ffmpeg", "-i", audio_file, "-f", "segment", "-segment_time", str(segment_seconds),
         "-c", "copy", pattern],
        check=True,
        capture_output=True,
    )
    return sorted(__import__("glob").glob(os.path.join(output_dir, "seg_*.webm")))


def transcribe_segments(segment_files, model_name, output_file):
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    with open(output_file, "w", encoding="utf-8") as f:
        for i, seg_file in enumerate(segment_files):
            segments, _ = model.transcribe(seg_file, vad_filter=True)
            for seg in segments:
                f.write(seg.text.strip() + "\n")
            f.flush()


def main():
    parser = argparse.ArgumentParser(description="监听频道新视频并转写")
    parser.add_argument("channel_url", help="YouTube频道URL")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--check-interval", type=int, default=300, help="检查间隔(秒，默认5分钟)")
    args = parser.parse_args()

    state = load_state()
    last_video_id = state.get("last_video_id")

    while True:
        videos = fetch_channel_videos(args.channel_url, max_results=3)
        if not videos:
            print("未能获取视频列表，等待下一次检查...")
            time.sleep(args.check_interval)
            continue

        newest_id = videos[0]["id"]
        newest_title = videos[0]["title"]

        if newest_id != last_video_id:
            print(f"检测到新视频: {newest_title} ({newest_id})")
            try:
                download_and_transcribe(args.channel_url, args.model)
                state["last_video_id"] = newest_id
                save_state(state)
                print("转写完成，等待下一次检查...")
            except Exception as e:
                print(f"转写失败: {e}")
        else:
            print(f"暂无新视频 (当前最新: {newest_title})")

        time.sleep(args.check_interval)


if __name__ == "__main__":
    main()