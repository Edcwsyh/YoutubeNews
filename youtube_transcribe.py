import argparse
import os

from whisper_utils import download_audio, split_audio, transcribe_segments


def main():
    parser = argparse.ArgumentParser(description="YouTube video to text transcription")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--output", default="transcript.txt", help="Output text file")
    parser.add_argument("--work-dir", default="/tmp/yt_transcribe", help="Working directory")
    parser.add_argument("--segment-seconds", type=int, default=300, help="Audio segment length in seconds")
    args = parser.parse_args()

    audio_file = download_audio(args.url, args.work_dir)
    print(f"Audio downloaded: {audio_file}")

    segment_files = split_audio(audio_file, args.work_dir, args.segment_seconds)
    print(f"Split into {len(segment_files)} segments")

    transcribe_segments(segment_files, args.model, args.output)
    print(f"Transcription complete: {args.output}")


if __name__ == "__main__":
    main()