import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import run_pipeline as pipeline


class PipelineChannelConfigTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("pipeline_channel_tests")
        self.logger.disabled = True
        self.channel = {
            "url": "https://www.youtube.com/@example",
            "name": "示例频道",
            "content_type": "live_replay_only",
        }
        self.config = {"youtube_channels": [self.channel]}
        self.args = SimpleNamespace(
            model="base", work_dir="/tmp/opencode/channel_tests",
            skip_transcribe=False, skip_archive=True, log_level="INFO",
        )

    def test_single_mode_passes_channel_config(self):
        with (
            patch("sys.argv", ["run_pipeline.py"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "run_pipeline_once", return_value=(True, "clip")) as run,
            self.assertRaises(SystemExit) as exit_context,
        ):
            pipeline.main()
        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(run.call_args.kwargs["channel_config"], self.channel)

    def test_invalid_config_stops_before_processing(self):
        self.channel["content_type"] = "typo"
        with (
            patch("sys.argv", ["run_pipeline.py"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "run_pipeline_once") as run,
            self.assertRaises(SystemExit) as exit_context,
        ):
            pipeline.main()
        self.assertEqual(exit_context.exception.code, 1)
        run.assert_not_called()

    def test_monitor_passes_filter_and_channel_config_and_saves_state(self):
        state = {"channels": {}}
        url = "https://www.youtube.com/watch?v=ready"
        with (
            patch("sys.argv", ["run_pipeline.py", "--monitor"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "load_state", return_value=state),
            patch.object(pipeline, "resolve_channel_to_latest_video", return_value=url) as resolve,
            patch.object(pipeline, "run_pipeline_once", return_value=(True, "ready")) as run,
            patch.object(pipeline, "save_state") as save,
            patch.object(pipeline.time, "sleep", side_effect=KeyboardInterrupt),
        ):
            pipeline.main()
        self.assertEqual(resolve.call_args.kwargs["content_type"], "live_replay_only")
        self.assertEqual(run.call_args.kwargs["channel_config"], self.channel)
        self.assertEqual(state["channels"][self.channel["url"]], "ready")
        save.assert_called_once_with(state)

    def test_monitor_with_no_ready_content_does_not_run_or_change_state(self):
        state = {"channels": {self.channel["url"]: "previous"}}
        with (
            patch("sys.argv", ["run_pipeline.py", "--monitor"]),
            patch.object(pipeline, "setup_logging", return_value=self.logger),
            patch.object(pipeline, "load_config", return_value=self.config),
            patch.object(pipeline, "load_state", return_value=state),
            patch.object(pipeline, "resolve_channel_to_latest_video", return_value=None) as resolve,
            patch.object(pipeline, "run_pipeline_once") as run,
            patch.object(pipeline, "save_state") as save,
            patch.object(pipeline.time, "sleep", side_effect=KeyboardInterrupt),
        ):
            pipeline.main()
        resolve.assert_called_once()
        run.assert_not_called()
        save.assert_not_called()
        self.assertEqual(state["channels"][self.channel["url"]], "previous")

    def test_run_once_passes_filter_and_cleanly_skips_empty_channel(self):
        with (
            patch.object(pipeline, "resolve_channel_to_latest_video", return_value=None) as resolve,
            patch.object(pipeline, "transcribe_video") as transcribe,
        ):
            result = pipeline.run_pipeline_once(
                self.channel["url"], self.args, self.logger, self.config, channel_config=self.channel,
            )
        self.assertEqual(result, (True, None))
        self.assertEqual(resolve.call_args.kwargs["content_type"], "live_replay_only")
        transcribe.assert_not_called()

    def test_direct_video_is_filtered_before_transcription(self):
        url = "https://www.youtube.com/watch?v=clip"
        for status in ("not_live", "is_live", "is_upcoming", "post_live", None):
            metadata = {
                "live_status": status, "available": True, "is_short": False,
            }
            with (
                self.subTest(status=status),
                patch.object(pipeline, "get_video_metadata", return_value=metadata),
                patch.object(pipeline, "transcribe_video") as transcribe,
            ):
                result = pipeline.run_pipeline_once(
                    url, self.args, self.logger, self.config, channel_config=self.channel,
                )
                self.assertEqual(result, (False, "clip"))
                transcribe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
