import os
import subprocess
import glob

import yt_dlp
from faster_whisper import WhisperModel


def download_audio(url, output_dir):
    """Download best audio from YouTube video"""
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
            raise FileNotFoundError("Audio file not found")
        audio_file = audio_files[0]
    return audio_file


def split_audio(audio_file, output_dir, segment_seconds=300):
    """Split audio into segments using ffmpeg"""
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "seg_%03d.webm")
    subprocess.run(
        ["ffmpeg", "-i", audio_file, "-f", "segment", "-segment_time", str(segment_seconds),
         "-c", "copy", pattern],
        check=True,
        capture_output=True,
    )
    return sorted(glob.glob(os.path.join(output_dir, "seg_*.webm")))


def transcribe_segments(segment_files, model_name="base", output_file=None):
    """Transcribe audio segments using faster-whisper.
    
    If output_file is provided, write segments to file.
    Returns (segments_list, info) tuple.
    """
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    results = []
    if output_file:
        f = open(output_file, "w", encoding="utf-8")
        write_to_file = True
    else:
        write_to_file = False

    for i, seg_file in enumerate(segment_files):
        segments, info = model.transcribe(seg_file, vad_filter=True)
        results.append((segments, info))
        if write_to_file:
            for seg in segments:
                f.write(seg.text.strip() + "\n")
            f.flush()

    if write_to_file:
        f.close()

    return results