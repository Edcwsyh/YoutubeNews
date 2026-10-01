import argparse
import glob
import os
import subprocess
import sys
import time

import yt_dlp
from faster_whisper import WhisperModel


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
        audio_files = glob.glob(os.path.join(output_dir, "audio.*"))
        if not audio_files:
            raise FileNotFoundError("Download completed but audio file not found")
        audio_file = audio_files[0]
    return audio_file


def split_audio(audio_file, output_dir, segment_seconds=300):
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "seg_%03d.webm")
    subprocess.run(
        ["ffmpeg", "-i", audio_file, "-f", "segment", "-segment_time", str(segment_seconds), "-c", "copy", pattern],
        check=True,
        capture_output=True,
    )
    return sorted(glob.glob(os.path.join(output_dir, "seg_*.webm")))


def transcribe_segments(segment_files, model_name, output_file):
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    with open(output_file, "w", encoding="utf-8") as f:
        for i, seg_file in enumerate(segment_files):
            print(f"Processing segment {i + 1}/{len(segment_files)}: {os.path.basename(seg_file)}")
            segments, _ = model.transcribe(seg_file, vad_filter=True)
            for seg in segments:
                f.write(seg.text.strip() + "\n")
            f.flush()
            print(f"  Done segment {i + 1}")


def main():
    parser = argparse.ArgumentParser(description="YouTube video to text transcription")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--output", default="transcript.txt", help="Output text file")
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="Working directory")
    parser.add_argument("--segment-seconds", type=int, default=300, help="Audio segment length in seconds")
    args = parser.parse_args()

    start_time = time.time()

    audio_file = download_audio(args.url, args.work_dir)
    print(f"Audio downloaded: {audio_file}")

    segment_files = split_audio(audio_file, args.work_dir, args.segment_seconds)
    print(f"Split into {len(segment_files)} segments")

    transcribe_segments(segment_files, args.model, args.output)
    print(f"Transcription complete: {args.output}")

    elapsed = time.time() - start_time
    print(f"Total time: {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
