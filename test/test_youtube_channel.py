import logging
import unittest
from unittest.mock import patch

import yt_dlp

import youtube_channel as channel


BASE_URL = "https://www.youtube.com/@example"


def video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def video_info(status="not_live", timestamp=100, **kwargs):
    info = {
        "title": "测试内容",
        "live_status": status,
        "timestamp": timestamp,
        "formats": [{"format_id": "audio", "acodec": "opus"}],
    }
    info.update(kwargs)
    return info


class ChannelSelectionTests(unittest.TestCase):
    def setUp(self):
        channel._metadata_cache.clear()
        self.logger = logging.getLogger("channel_selection_tests")
        self.logger.disabled = True
        self.responses = {
            f"{BASE_URL}/videos": {"entries": []},
            f"{BASE_URL}/streams": {"entries": []},
        }
        patcher = patch("youtube_channel.yt_dlp.YoutubeDL")
        self.addCleanup(patcher.stop)
        self.addCleanup(channel._metadata_cache.clear)
        self.ydl = patcher.start()
        self.extract = self.ydl.return_value.__enter__.return_value.extract_info
        self.extract.side_effect = self.extract_info

    def extract_info(self, url, download):
        self.assertFalse(download)
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    def add_tab(self, tab, *video_ids):
        self.responses[f"{BASE_URL}/{tab}"] = {
            "entries": [{"id": video_id} for video_id in video_ids],
        }

    def resolve(self, content_type="all", url=BASE_URL):
        return channel.resolve_channel_to_latest_video(
            url, logger=self.logger, content_type=content_type,
        )

    def test_video_only_uses_videos_tab_and_skips_replays(self):
        self.add_tab("videos", "replay", "clip")
        self.responses[video_url("replay")] = video_info("was_live", 200)
        self.responses[video_url("clip")] = video_info("not_live", 100)
        self.assertEqual(self.resolve("video_only"), video_url("clip"))
        urls = [call.args[0] for call in self.extract.call_args_list]
        self.assertNotIn(f"{BASE_URL}/streams", urls)

    def test_live_replay_only_skips_live_upcoming_processing_and_ordinary(self):
        self.add_tab("streams", "upcoming", "live", "processing", "clip", "ready")
        for video_id, status in (
            ("upcoming", "is_upcoming"), ("live", "is_live"),
            ("processing", "post_live"), ("clip", "not_live"), ("ready", "was_live"),
        ):
            self.responses[video_url(video_id)] = video_info(status)
        self.assertEqual(self.resolve("live_replay_only"), video_url("ready"))
        urls = [call.args[0] for call in self.extract.call_args_list]
        self.assertNotIn(f"{BASE_URL}/videos", urls)

    def test_all_compares_actual_release_time_of_both_types(self):
        self.add_tab("videos", "clip")
        self.add_tab("streams", "replay")
        self.responses[video_url("clip")] = video_info("not_live", 200)
        self.responses[video_url("replay")] = video_info("was_live", 50, release_timestamp=300)
        self.assertEqual(self.resolve(), video_url("replay"))

    def test_all_can_select_newer_ordinary_video(self):
        self.add_tab("videos", "clip")
        self.add_tab("streams", "replay")
        self.responses[video_url("clip")] = video_info("not_live", 300)
        self.responses[video_url("replay")] = video_info("was_live", 200)
        self.assertEqual(self.resolve(), video_url("clip"))

    def test_missing_streams_tab_does_not_block_videos(self):
        self.add_tab("videos", "clip")
        self.responses[video_url("clip")] = video_info()
        self.responses[f"{BASE_URL}/streams"] = yt_dlp.utils.DownloadError(
            "This channel does not have a streams tab",
        )
        self.assertEqual(self.resolve(), video_url("clip"))
        self.assertIsNone(self.resolve("live_replay_only"))

    def test_network_error_is_not_treated_as_missing_tab(self):
        self.responses[f"{BASE_URL}/streams"] = yt_dlp.utils.DownloadError("connection timeout")
        with self.assertRaises(yt_dlp.utils.DownloadError):
            self.resolve()

    def test_empty_tabs_return_none(self):
        self.assertIsNone(self.resolve())

    def test_shorts_are_skipped_without_duration_heuristics(self):
        self.responses[f"{BASE_URL}/videos"] = {"entries": [
            {"id": "short1", "url": "https://www.youtube.com/shorts/short1"},
            {"id": "short2", "title": "片段 #Shorts"},
            {"id": "clip"},
        ]}
        self.responses[video_url("clip")] = video_info(duration=30)
        self.assertEqual(self.resolve("video_only"), video_url("clip"))
        self.assertEqual(self.extract.call_count, 2)

    def test_metadata_error_skips_candidate_and_is_not_cached(self):
        self.add_tab("videos", "failed", "clip")
        self.responses[video_url("failed")] = yt_dlp.utils.DownloadError("temporary error")
        self.responses[video_url("clip")] = video_info()
        self.assertEqual(self.resolve("video_only"), video_url("clip"))
        self.assertNotIn(video_url("failed"), channel._metadata_cache)
        self.responses[video_url("failed")] = video_info(timestamp=200)
        self.assertEqual(self.resolve("video_only"), video_url("failed"))

    def test_ready_metadata_is_cached_but_transitional_statuses_are_not(self):
        url = video_url("replay")
        for status in ("is_upcoming", "is_live", "post_live", "was_live"):
            self.responses[url] = video_info(status)
            metadata = channel.get_video_metadata(url, logger=self.logger)
            self.assertEqual(metadata["live_status"], status)
        channel.get_video_metadata(url, logger=self.logger)
        self.assertEqual(self.extract.call_count, 4)

    def test_no_formats_is_not_ready_or_cached(self):
        url = video_url("replay")
        self.responses[url] = video_info("was_live", formats=[])
        metadata = channel.get_video_metadata(url, logger=self.logger)
        self.assertFalse(channel.is_processable_video(metadata, "live_replay_only"))
        self.assertNotIn(url, channel._metadata_cache)
        self.responses[url] = video_info("was_live")
        metadata = channel.get_video_metadata(url, logger=self.logger)
        self.assertTrue(channel.is_processable_video(metadata, "live_replay_only"))

    def test_unknown_status_is_not_guessed_or_cached(self):
        url = video_url("unknown")
        self.responses[url] = video_info(None)
        metadata = channel.get_video_metadata(url, logger=self.logger)
        self.assertFalse(channel.is_processable_video(metadata))
        self.assertNotIn(url, channel._metadata_cache)

    def test_cache_is_bounded_and_keeps_recently_used_entries(self):
        with patch("youtube_channel.METADATA_CACHE_LIMIT", 2):
            for video_id in ("first", "second", "first", "third"):
                self.responses[video_url(video_id)] = video_info()
                channel.get_video_metadata(video_url(video_id), logger=self.logger)
        self.assertEqual(list(channel._metadata_cache), [video_url("first"), video_url("third")])
        self.assertEqual(self.extract.call_count, 3)

    def test_listing_and_metadata_requests_never_download_media(self):
        self.add_tab("videos", "clip", "older")
        self.responses[video_url("clip")] = video_info()
        self.assertEqual(self.resolve("video_only"), video_url("clip"))
        options = [call.args[0] for call in self.ydl.call_args_list]
        self.assertTrue(options[0]["extract_flat"])
        self.assertTrue(options[0]["lazy_playlist"])
        self.assertEqual(options[0]["playlistend"], 20)
        self.assertTrue(all(option["skip_download"] for option in options))
        self.assertEqual(self.extract.call_count, 2)

    def test_candidate_limit_is_enforced(self):
        ids = [f"live{i}" for i in range(20)]
        self.add_tab("streams", *ids, "ready")
        for video_id in ids:
            self.responses[video_url(video_id)] = video_info("is_live")
        self.assertIsNone(self.resolve("live_replay_only"))
        self.assertEqual(self.extract.call_count, 21)

    def test_existing_tab_and_sort_parameters_are_normalized(self):
        self.add_tab("videos", "clip")
        self.responses[video_url("clip")] = video_info()
        self.assertEqual(
            self.resolve("video_only", f"{BASE_URL}/streams?view=0&sort=p"), video_url("clip"),
        )
        for url, expected in (
            ("https://www.youtube.com/channel/UC123/videos/", "https://www.youtube.com/channel/UC123"),
            ("https://www.youtube.com/user/example", "https://www.youtube.com/user/example"),
            ("https://www.youtube.com/c/example", "https://www.youtube.com/c/example"),
        ):
            self.assertEqual(channel._channel_base_url(url), expected)

    def test_invalid_content_type_fails_before_network_requests(self):
        for content_type in ("videos_only", "", None, []):
            with self.subTest(content_type=content_type), self.assertRaises(ValueError):
                self.resolve(content_type)
        self.extract.assert_not_called()

    def test_date_fallback_and_missing_dates(self):
        self.assertEqual(channel._publication_timestamp({"upload_date": "19700102"}), 86400)
        self.assertIsNone(channel._publication_timestamp({"upload_date": "bad"}))

    def test_all_does_not_guess_order_when_publication_time_is_missing(self):
        self.add_tab("videos", "clip")
        self.add_tab("streams", "replay")
        self.responses[video_url("clip")] = video_info(timestamp=None)
        self.responses[video_url("replay")] = video_info("was_live", 200)
        with self.assertRaises(RuntimeError):
            self.resolve()
        self.assertNotIn(video_url("clip"), channel._metadata_cache)


if __name__ == "__main__":
    unittest.main()
