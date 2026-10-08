"""按频道内容类型选择最新可处理的视频，不下载媒体文件。"""

import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from itertools import islice
from urllib.parse import urlsplit, urlunsplit

import yt_dlp


CONTENT_TYPES = ("all", "video_only", "live_replay_only")
CANDIDATE_LIMIT = 20
METADATA_CACHE_LIMIT = 512
_metadata_cache = OrderedDict()


def validate_content_type(content_type):
    if content_type not in CONTENT_TYPES:
        raise ValueError(
            f"无效的 content_type={content_type!r}，可选值: {', '.join(CONTENT_TYPES)}"
        )
    return content_type


def _channel_base_url(channel_url):
    parts = urlsplit(channel_url)
    path_parts = parts.path.strip("/").split("/")
    if path_parts[0].startswith("@"):
        channel_path = "/" + path_parts[0]
    elif path_parts[0] in {"channel", "user", "c"} and len(path_parts) >= 2:
        channel_path = "/" + "/".join(path_parts[:2])
    else:
        raise ValueError(f"不支持的频道 URL 格式: {channel_url}")
    # 去掉已有标签页、排序参数，始终使用标签页默认的最新内容顺序。
    return urlunsplit((parts.scheme, parts.netloc, channel_path, "", ""))


def _ydl_options(logger):
    return {
        "quiet": True,
        "logger": logger,
        "skip_download": True,
        "socket_timeout": 10,
        "retries": 2,
        "extractor_retries": 2,
    }


def _get_tab_entries(channel_url, tab, logger):
    tab_url = f"{_channel_base_url(channel_url)}/{tab}"
    options = _ydl_options(logger)
    options.update({
        "extract_flat": True,
        "lazy_playlist": True,
        "playlistend": CANDIDATE_LIMIT,
    })
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            result = ydl.extract_info(tab_url, download=False)
            if result is None:
                raise RuntimeError(f"无法获取频道标签页: {tab_url}")
            return list(islice(result.get("entries") or [], CANDIDATE_LIMIT))
    except yt_dlp.utils.DownloadError as e:
        # 没有对应标签页是正常情况；网络/解析失败则交给流水线重试。
        if f"This channel does not have a {tab} tab" in str(e):
            logger.info(f"频道没有 {tab} 标签页: {channel_url}")
            return []
        raise


def _is_short(info):
    urls = (info.get("url") or "", info.get("webpage_url") or "")
    return (
        any("/shorts/" in url for url in urls)
        or "#shorts" in (info.get("title") or "").lower()
    )


def _publication_timestamp(info):
    # 直播/首映按实际发布（开播）时间比较，普通视频按上传发布时间比较。
    for field in ("release_timestamp", "timestamp"):
        value = info.get(field)
        if isinstance(value, (int, float)):
            return value
    for field in ("release_date", "upload_date"):
        value = info.get(field)
        if value:
            try:
                return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()
            except (TypeError, ValueError):
                pass
    return None


def get_video_metadata(video_url, logger=None):
    """仅缓存已可用的普通视频/完整回放，缓存有上限且仅在当前进程内保存。"""
    if logger is None:
        logger = logging.getLogger(__name__)
    if video_url in _metadata_cache:
        _metadata_cache.move_to_end(video_url)
        return _metadata_cache[video_url]

    options = _ydl_options(logger)
    options.update({"noplaylist": True, "ignore_no_formats_error": True})
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        logger.warning(f"查询视频元数据失败，稍后再检查: {video_url}: {e}")
        return None
    if not info:
        return None

    metadata = {
        "title": info.get("title") or video_url,
        "live_status": info.get("live_status"),
        "timestamp": _publication_timestamp(info),
        "available": bool(info.get("formats")),
        "is_short": _is_short(info),
        "url": video_url,
    }
    if (
        metadata["live_status"] in {"not_live", "was_live"}
        and metadata["available"]
        and metadata["timestamp"] is not None
    ):
        _metadata_cache[video_url] = metadata
        while len(_metadata_cache) > METADATA_CACHE_LIMIT:
            _metadata_cache.popitem(last=False)
    return metadata


def is_processable_video(metadata, content_type="all"):
    validate_content_type(content_type)
    if not metadata or not metadata["available"] or metadata["is_short"]:
        return False
    allowed_statuses = {
        "all": {"not_live", "was_live"},
        "video_only": {"not_live"},
        "live_replay_only": {"was_live"},
    }
    return metadata["live_status"] in allowed_statuses[content_type]


def resolve_channel_to_latest_video(channel_url, logger=None, max_age_hours=12, content_type="all"):
    """每个所需标签页最多检查 20 条，选择最新匹配项；没有匹配项返回 None。"""
    if logger is None:
        logger = logging.getLogger(__name__)
    validate_content_type(content_type)
    logger.info(f"解析频道最新内容: {channel_url}, content_type={content_type}")
    tabs = {
        "all": ("videos", "streams"),
        "video_only": ("videos",),
        "live_replay_only": ("streams",),
    }[content_type]
    candidates = []
    for tab in tabs:
        tab_content_type = "video_only" if tab == "videos" else "live_replay_only"
        for entry in _get_tab_entries(channel_url, tab, logger):
            if not entry or not entry.get("id") or _is_short(entry):
                continue
            video_url = f"https://www.youtube.com/watch?v={entry['id']}"
            metadata = get_video_metadata(video_url, logger=logger)
            if not is_processable_video(metadata, tab_content_type):
                status = metadata["live_status"] if metadata else "unknown"
                logger.debug(f"跳过不可处理的候选: {video_url}, live_status={status}")
                continue
            # 标签页默认按最新排序，只需找到每个标签页的第一个可用匹配项。
            candidates.append(metadata)
            break

    if not candidates:
        logger.info(f"频道近期没有符合 {content_type} 的可处理内容，下轮再检查: {channel_url}")
        return None
    if len(candidates) > 1 and any(item["timestamp"] is None for item in candidates):
        # all 模式无法确定哪一项更新时不能猜测，避免处理后在两项间来回跳转。
        raise RuntimeError(f"候选内容缺少发布时间，无法比较最新内容: {channel_url}")
    latest = max(candidates, key=lambda item: item["timestamp"] or 0)
    if latest["timestamp"] is not None and latest["timestamp"] < time.time() - max_age_hours * 3600:
        logger.info(f"最近 {max_age_hours}h 无新匹配内容，使用最新可处理内容")
    logger.info(f"选择内容: {latest['title']} ({latest['url']})")
    return latest["url"]
