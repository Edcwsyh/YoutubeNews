import logging
import subprocess
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import run_pipeline as pipeline


class AIModelConfigTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(
            model="base", ai_model=None, work_dir="/tmp/opencode/ai_model_tests",
            skip_transcribe=True, skip_archive=True, log_level="INFO",
        )
        self.channel = {
            "url": "https://www.youtube.com/@example",
            "name": "示例频道",
        }
        self.config = {"youtube_channels": [self.channel], "ai_max_retries": 2}
        self.logger = Mock(spec=logging.Logger)

    def resolve(self):
        return pipeline.resolve_ai_model(self.args, self.config, self.channel)

    def test_cli_overrides_channel_and_global(self):
        self.args.ai_model = "cli/model#high"
        self.channel["ai_model"] = "channel/model"
        self.config["ai_model"] = "global/model"
        self.assertEqual(self.resolve(), "cli/model#high")

    def test_channel_overrides_global(self):
        self.channel["ai_model"] = "channel/model"
        self.config["ai_model"] = "global/model"
        self.assertEqual(self.resolve(), "channel/model")

    def test_global_is_used_without_cli_or_channel_override(self):
        self.config["ai_model"] = "global/model"
        self.assertEqual(self.resolve(), "global/model")

    def test_missing_or_null_values_inherit_default(self):
        self.assertIsNone(self.resolve())
        self.channel["ai_model"] = None
        self.config["ai_model"] = None
        self.assertIsNone(self.resolve())
        self.config["ai_model"] = "global/model"
        self.assertEqual(self.resolve(), "global/model")
        # 兼容旧调用方未提供 ai_model 属性的参数对象。
        del self.args.ai_model
        self.assertEqual(self.resolve(), "global/model")

    def test_model_with_nested_id_and_variant_is_preserved(self):
        self.config["ai_model"] = "  provider/vendor/model#high  "
        self.assertEqual(self.resolve(), "provider/vendor/model#high")

    def test_invalid_effective_model_is_rejected(self):
        for value in (
            "", "   ", False, 123, [], {}, "model", "/model", "provider/",
            "provider//model", "provider/model/", "provider/model#", "provider/#high",
            "provider/model#high#low", "provider#high/model", "provider/model name",
            "provider name/model", "provider/model\nname", "provider/model\x00name",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.args.ai_model = value
                self.resolve()

    def test_invalid_selected_value_does_not_fall_back(self):
        self.config["ai_model"] = "global/model"
        self.channel["ai_model"] = ""
        with self.assertRaises(ValueError):
            self.resolve()

    def test_overridden_values_do_not_affect_effective_model(self):
        self.args.ai_model = "cli/model"
        self.channel["ai_model"] = "invalid"
        self.config["ai_model"] = 123
        self.assertEqual(self.resolve(), "cli/model")

    def test_cli_ai_model_is_independent_of_whisper_model(self):
        with (
            patch("sys.argv", ["run_pipeline.py", "--model", "tiny", "--ai-model", "cli/model#high"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "run_pipeline_once", return_value=(True, "clip")) as run,
            self.assertRaises(SystemExit) as exit_context,
        ):
            pipeline.main()
        self.assertEqual(exit_context.exception.code, 0)
        args = run.call_args.args[1]
        self.assertEqual(args.model, "tiny")
        self.assertEqual(args.ai_model, "cli/model#high")

    def test_bad_model_config_stops_before_processing_in_both_modes(self):
        self.config["ai_model"] = "invalid"
        for mode in ([], ["--monitor"]):
            with (
                self.subTest(mode=mode),
                patch("sys.argv", ["run_pipeline.py", *mode]),
                patch.object(pipeline, "setup_logging", return_value=self.logger),
                patch.object(pipeline, "load_config", return_value=self.config),
                patch.object(pipeline, "run_pipeline_once") as run,
                patch.object(pipeline, "resolve_channel_to_latest_video") as resolve,
                self.assertRaises(SystemExit) as exit_context,
            ):
                pipeline.main()
                self.assertEqual(exit_context.exception.code, 1)
                run.assert_not_called()
                resolve.assert_not_called()

    def test_monitor_passes_cli_override_alongside_channel_config(self):
        self.config["ai_model"] = "global/model"
        self.channel["ai_model"] = "channel/model"
        with (
            patch("sys.argv", ["run_pipeline.py", "--monitor", "--ai-model", "cli/model#high"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "load_state", return_value={"channels": {}}),
            patch.object(pipeline, "resolve_channel_to_latest_video", return_value="https://www.youtube.com/watch?v=clip"),
            patch.object(pipeline, "run_pipeline_once", return_value=(False, "clip")) as run,
            patch.object(pipeline.time, "sleep", side_effect=KeyboardInterrupt),
        ):
            pipeline.main()
        args = run.call_args.args[1]
        channel = run.call_args.kwargs["channel_config"]
        self.assertEqual(channel, self.channel)
        self.assertEqual(pipeline.resolve_ai_model(args, self.config, channel), "cli/model#high")

    def run_once(self, command_results):
        with (
            patch("subprocess.run", side_effect=command_results) as run,
            patch.object(pipeline.os.path, "exists", return_value=True),
            patch.object(pipeline.os.path, "getsize", return_value=100),
            patch.object(pipeline, "transcribe_video") as transcribe,
            patch.object(pipeline, "push_reports", return_value=True) as push,
            patch.object(pipeline, "ensure_directory", side_effect=lambda path: Path(path)),
            patch.object(pipeline, "publish_report", return_value="reports/本次主题.md"),
            patch.object(pipeline, "archive_files") as archive,
        ):
            result = pipeline.run_pipeline_once(
                "https://www.youtube.com/watch?v=clip", self.args,
                self.logger, self.config, channel_config=self.channel,
            )
        transcribe.assert_not_called()
        archive.assert_not_called()
        return result, run, push

    @staticmethod
    def command_result(returncode=0, stderr=""):
        return subprocess.CompletedProcess([], returncode, stdout="AI output", stderr=stderr)

    @staticmethod
    def option(command, name):
        return command[command.index(name) + 1]

    def test_configured_model_is_passed_to_run_and_session_is_deleted(self):
        self.channel["ai_model"] = "channel/model#high"
        result, run, push = self.run_once([self.command_result(), self.command_result()])
        self.assertEqual(result, (True, "clip"))
        command, deletion = [call.args[0] for call in run.call_args_list]
        self.assertEqual(command[:2], ["opencode", "run"])
        self.assertEqual(self.option(command, "--model"), "channel/model#high")
        self.assertEqual(deletion, ["opencode", "session", "delete", self.option(command, "--session")])
        self.logger.info.assert_any_call("AI分析模型: channel/model#high")
        push.assert_called_once()

    def test_retries_keep_model_and_session_even_if_config_changes(self):
        self.config["ai_model"] = "global/model#high"
        commands = []

        def execute(command, **kwargs):
            commands.append(command)
            if len(commands) == 1:
                self.args.ai_model = "changed/model"
                self.channel["ai_model"] = "changed/channel-model"
                self.config["ai_model"] = "changed/global-model"
                return self.command_result(1, "temporary failure")
            return self.command_result()

        result, run, push = self.run_once(execute)
        self.assertEqual(result, (True, "clip"))
        self.assertEqual(len(commands), 3)
        for command in commands[:2]:
            self.assertEqual(self.option(command, "--model"), "global/model#high")
        self.assertEqual(
            self.option(commands[0], "--session"), self.option(commands[1], "--session"),
        )
        self.assertEqual(commands[1][-1], "继续执行分析")
        push.assert_called_once()

    def test_default_model_is_not_explicitly_passed_on_initial_run_or_retry(self):
        result, run, push = self.run_once([
            self.command_result(1, "temporary failure"), self.command_result(), self.command_result(),
        ])
        self.assertEqual(result, (True, "clip"))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(all("--model" not in command for command in commands))
        self.assertEqual(
            self.option(commands[0], "--session"), self.option(commands[1], "--session"),
        )
        self.logger.info.assert_any_call("AI分析模型: OpenCode 默认模型")

    def test_unavailable_model_does_not_fall_back_or_delete_failed_session(self):
        self.config["ai_model"] = "provider/unavailable"
        result, run, push = self.run_once([
            self.command_result(1, "Unknown model"), self.command_result(1, "Unknown model"),
        ])
        self.assertEqual(result, (False, "clip"))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(command[:2] == ["opencode", "run"] for command in commands))
        self.assertTrue(all(self.option(command, "--model") == "provider/unavailable" for command in commands))
        self.assertEqual(
            self.option(commands[0], "--session"), self.option(commands[1], "--session"),
        )
        push.assert_not_called()
        self.logger.error.assert_called_once()

    def test_cleanup_failure_still_does_not_block_pipeline(self):
        self.config["ai_model"] = "provider/model"
        result, run, push = self.run_once([
            self.command_result(), self.command_result(1, "delete failed"),
        ])
        self.assertEqual(result, (True, "clip"))
        push.assert_called_once()
        self.logger.warning.assert_called_once()

    def test_bad_model_in_run_once_is_rejected_before_transcription(self):
        self.args.skip_transcribe = False
        self.config["ai_model"] = "invalid"
        with (
            patch.object(pipeline, "transcribe_video") as transcribe,
            patch.object(pipeline, "get_video_metadata") as metadata,
            patch("subprocess.run") as run,
        ):
            result = pipeline.run_pipeline_once(
                "https://www.youtube.com/watch?v=clip", self.args,
                self.logger, self.config, channel_config=self.channel,
            )
        self.assertEqual(result, (False, None))
        transcribe.assert_not_called()
        metadata.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
