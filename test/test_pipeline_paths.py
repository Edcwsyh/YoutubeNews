import json
import logging
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run_pipeline as pipeline


class PipelineWorkingDirectoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.base_dir = Path(temporary.name)
        original_dir = os.getcwd()
        os.chdir(self.base_dir)
        self.addCleanup(os.chdir, original_dir)
        self.logger = Mock(spec=logging.Logger)
        self.args = SimpleNamespace(
            model="base", ai_model=None, work_dir="tmp/yt_transcribe",
            skip_transcribe=False, skip_archive=False, log_level="INFO",
        )
        self.config = {"youtube_channels": [], "ai_max_retries": 2}

    def test_config_is_read_from_current_directory_after_import(self):
        config = {"youtube_channels": [], "ai_model": "example/model"}
        (self.base_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(pipeline.load_config(), config)

    def test_missing_local_config_does_not_fall_back_to_script_directory(self):
        with self.assertRaises(FileNotFoundError):
            pipeline.load_config()

    def test_state_is_saved_and_loaded_in_current_directory(self):
        state = {"channels": {"example": "video"}}
        self.assertEqual(pipeline.load_state(), {"channels": {}})
        pipeline.save_state(state)
        self.assertTrue((self.base_dir / ".pipeline_state.json").is_file())
        self.assertEqual(pipeline.load_state(), state)

    def test_logging_file_is_created_in_current_directory(self):
        with patch.object(pipeline.logging, "basicConfig") as configure:
            pipeline.setup_logging()
        handlers = configure.call_args.kwargs["handlers"]
        try:
            self.assertEqual(handlers[1].baseFilename, str(self.base_dir / "pipeline.log"))
            self.assertTrue((self.base_dir / "pipeline.log").is_file())
        finally:
            for handler in handlers:
                handler.close()

    def test_archive_uses_pipeline_working_directory(self):
        transcript = self.base_dir / "transcript.txt"
        transcript.write_text("测试转写", encoding="utf-8")
        pipeline.archive_files(str(self.base_dir), str(transcript), logger=self.logger)
        pipeline.archive_files(str(self.base_dir), str(transcript), logger=self.logger)
        archive = self.base_dir / "archive"
        self.assertEqual(len(list(archive.glob("transcript_*.txt"))), 2)
        self.assertTrue(all(p.read_text(encoding="utf-8") == "测试转写" for p in archive.glob("transcript_*.txt")))

    def run_once(self, results=(1, 0)):
        commands = []

        def transcribe(url, **kwargs):
            self.assertEqual(kwargs["output"], str(self.base_dir / "transcript.txt"))
            self.assertEqual(kwargs["work_dir"], str(self.base_dir / "tmp" / "yt_transcribe"))
            Path(kwargs["work_dir"]).mkdir(parents=True, exist_ok=True)
            Path(kwargs["output"]).write_text("测试转写", encoding="utf-8")

        run_results = iter(results)

        def execute(command, **kwargs):
            self.assertEqual(kwargs["cwd"], str(self.base_dir))
            commands.append(command)
            if command[:2] == ["opencode", "run"]:
                code = next(run_results)
                if code == 0:
                    staging_dir = Path(re.search(r"本次报告输出目录为 (.*?)。", commands[0][-1]).group(1))
                    (staging_dir / "本次主题.md").write_text("本次报告", encoding="utf-8")
                return subprocess.CompletedProcess(command, code, stdout="", stderr="failure" if code else "")
            self.assertEqual(command[:3], ["opencode", "session", "delete"])
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with (
            patch.object(pipeline, "get_video_metadata", return_value={
                "live_status": "not_live", "available": True, "is_short": False,
            }),
            patch.object(pipeline, "transcribe_video", side_effect=transcribe) as transcribe_mock,
            patch("subprocess.run", side_effect=execute) as run,
            patch("telegram_push.push_result") as push,
        ):
            result = pipeline.run_pipeline_once(
                "https://www.youtube.com/watch?v=clip", self.args, self.logger, self.config,
            )
        return result, commands, transcribe_mock, run, push

    def test_transcription_ai_retry_cleanup_push_and_archive_share_current_directory(self):
        temporary_audio = self.base_dir / "tmp" / "yt_transcribe"
        temporary_audio.mkdir(parents=True)
        (temporary_audio / "old_audio.webm").write_text("旧音频", encoding="utf-8")
        result, commands, transcribe, run, push = self.run_once()
        self.assertEqual(result, (True, "clip"))
        self.assertFalse((temporary_audio / "old_audio.webm").exists())
        self.assertEqual(len(commands), 3)
        self.assertIn(str(self.base_dir / "transcript.txt"), commands[0][-1])
        self.assertIn(str(self.base_dir / "reports" / ".pending"), commands[0][-1])
        session = commands[0][commands[0].index("--session") + 1]
        self.assertEqual(commands[1][commands[1].index("--session") + 1], session)
        self.assertEqual(commands[2], ["opencode", "session", "delete", session])
        self.assertEqual(push.call_args.args[0], str(self.base_dir / "reports" / "本次主题.md"))
        self.assertEqual(len(list((self.base_dir / "archive").glob("????????_本次主题.md"))), 1)
        self.assertEqual(list((self.base_dir / "reports").glob("*.md")), [])
        transcribe.assert_called_once()
        self.assertEqual(os.getcwd(), str(self.base_dir))

    def test_skip_transcribe_requires_local_transcript_and_does_not_call_ai(self):
        self.args.skip_transcribe = True
        result, commands, transcribe, run, push = self.run_once()
        self.assertEqual(result, (False, None))
        self.assertEqual(commands, [])
        transcribe.assert_not_called()
        run.assert_not_called()
        push.assert_not_called()

    def test_audio_directory_cannot_delete_current_directory_or_ancestors(self):
        marker = self.base_dir / "keep.txt"
        marker.write_text("保留", encoding="utf-8")
        for work_dir in (".", "..", str(self.base_dir), "/"):
            with self.subTest(work_dir=work_dir):
                self.args.work_dir = work_dir
                result, commands, transcribe, run, push = self.run_once()
                self.assertEqual(result, (False, "clip"))
                self.assertTrue(marker.is_file())
                transcribe.assert_not_called()
                run.assert_not_called()
                push.assert_not_called()

    def test_audio_symlink_to_current_directory_is_rejected(self):
        (self.base_dir / "audio_link").symlink_to(self.base_dir, target_is_directory=True)
        self.args.work_dir = "audio_link"
        result, commands, transcribe, run, push = self.run_once()
        self.assertEqual(result, (False, "clip"))
        self.assertTrue((self.base_dir / "audio_link").is_symlink())
        transcribe.assert_not_called()
        run.assert_not_called()
        push.assert_not_called()

    def test_cli_default_audio_directory_is_relative_to_callers_directory(self):
        channel = {"url": "https://www.youtube.com/@example"}
        with (
            patch("sys.argv", [str(Path(pipeline.__file__).resolve())]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value={"youtube_channels": [channel]}),
            patch.object(pipeline, "run_pipeline_once", return_value=(True, None)) as run,
            self.assertRaises(SystemExit) as exit_context,
        ):
            pipeline.main()
        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(run.call_args.args[1].work_dir, "tmp/yt_transcribe")
        self.assertEqual(os.getcwd(), str(self.base_dir))

    def test_skill_paths_refer_to_session_directory_not_skill_directory(self):
        skill = Path(pipeline.__file__).parent / ".opencode" / "skills" / "newsanalysis" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        self.assertNotIn("/home/Edcwsyh/work", content)
        self.assertIn("不是本 skill 文件所在目录", content)
        self.assertIn("`transcript.txt`", content)
        self.assertIn("`reports/`", content)


if __name__ == "__main__":
    unittest.main()
