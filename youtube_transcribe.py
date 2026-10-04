import argparse
import logging
import os
import sys

from whisper_utils import download_audio, split_audio, transcribe_segments, get_logger


def setup_logging(level=logging.INFO):
    log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


def transcribe_video(url, model="base", output="transcript.txt", work_dir="/tmp/yt_transcribe", segment_seconds=300, log_level="INFO", logger=None):
    """直接可调用的转写函数"""
    if logger is None:
        logger = setup_logging(getattr(logging, log_level))
    whisper_logger = get_logger("whisper_utils")
    whisper_logger.setLevel(getattr(logging, log_level))

    logger.info(f"开始转写: {url}")
    logger.debug(f"参数: model={model}, output={output}, work_dir={work_dir}, segment_seconds={segment_seconds}")

    audio_file = download_audio(url, work_dir, logger=whisper_logger)
    logger.info(f"音频下载完成: {audio_file}")

    segment_files = split_audio(audio_file, work_dir, segment_seconds, logger=whisper_logger)
    logger.info(f"切分完成: {len(segment_files)} 个片段")

    transcribe_segments(segment_files, model, output, logger=whisper_logger)
    logger.info(f"转写完成: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description="YouTube video to text transcription")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--output", default="transcript.txt", help="Output text file")
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="Working directory")
    parser.add_argument("--segment-seconds", type=int, default=300, help="Audio segment length in seconds")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level")
    args = parser.parse_args()

    transcribe_video(args.url, args.model, args.output, args.work_dir, args.segment_seconds, args.log_level)


if __name__ == "__main__":
    main()