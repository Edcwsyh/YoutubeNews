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

    logger = setup_logging(getattr(logging, args.log_level))
    whisper_logger = get_logger("whisper_utils")
    whisper_logger.setLevel(getattr(logging, args.log_level))

    logger.info(f"开始转写: {args.url}")
    logger.debug(f"参数: model={args.model}, output={args.output}, work_dir={args.work_dir}, segment_seconds={args.segment_seconds}")

    audio_file = download_audio(args.url, args.work_dir, logger=whisper_logger)
    logger.info(f"音频下载完成: {audio_file}")

    segment_files = split_audio(audio_file, args.work_dir, args.segment_seconds, logger=whisper_logger)
    logger.info(f"切分完成: {len(segment_files)} 个片段")

    transcribe_segments(segment_files, args.model, args.output, logger=whisper_logger)
    logger.info(f"转写完成: {args.output}")


if __name__ == "__main__":
    main()