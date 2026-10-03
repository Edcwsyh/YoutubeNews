import os
import subprocess
import glob
import logging

import yt_dlp
from faster_whisper import WhisperModel


def get_logger(name="whisper_utils"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def download_audio(url, output_dir, logger=None):
    """Download best audio from YouTube video"""
    if logger is None:
        logger = get_logger()
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": os.path.join(output_dir, "audio.%(ext)s"),
        "quiet": True,
    }
    logger.info(f"下载音频: {url} -> {output_dir}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    audio_file = ydl.prepare_filename(info)
    if not os.path.exists(audio_file):
        audio_files = glob.glob(os.path.join(output_dir, "audio.*"))
        if not audio_files:
            raise FileNotFoundError("Audio file not found")
        audio_file = audio_files[0]
    logger.info(f"音频下载完成: {audio_file} ({os.path.getsize(audio_file)} bytes)")
    return audio_file


def split_audio(audio_file, output_dir, segment_seconds=300, logger=None):
    """Split audio into segments using ffmpeg"""
    if logger is None:
        logger = get_logger()
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "seg_%03d.webm")
    logger.info(f"切分音频: {audio_file} -> {pattern} (每段 {segment_seconds}s)")
    subprocess.run(
        ["ffmpeg", "-i", audio_file, "-f", "segment", "-segment_time", str(segment_seconds),
         "-c", "copy", pattern],
        check=True,
        capture_output=True,
    )
    segments = sorted(glob.glob(os.path.join(output_dir, "seg_*.webm")))
    logger.info(f"切分完成: {len(segments)} 个片段")
    return segments


def transcribe_segments(segment_files, model_name="base", output_file=None, logger=None):
    """Transcribe audio segments using faster-whisper.
    
    If output_file is provided, write segments to file.
    Returns (segments_list, info) tuple.
    """
    if logger is None:
        logger = get_logger()
    logger.info(f"加载模型: {model_name}")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    results = []
    if output_file:
        f = open(output_file, "w", encoding="utf-8")
        write_to_file = True
        logger.info(f"转写输出到: {output_file}")
    else:
        write_to_file = False

    for i, seg_file in enumerate(segment_files):
        logger.info(f"转写片段 {i+1}/{len(segment_files)}: {seg_file}")
        segments_gen, info = model.transcribe(seg_file, vad_filter=True)
        segments = list(segments_gen)  # generator -> list
        results.append((segments, info))
        if write_to_file:
            for seg in segments:
                f.write(seg.text.strip() + "\n")
            f.flush()
        logger.debug(f"  片段 {i+1} 完成: {len(segments)} 个语音段")

    if write_to_file:
        f.close()
        logger.info(f"转写完成，结果已写入: {output_file}")

    return results