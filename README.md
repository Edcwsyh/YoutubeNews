# YouTube News Pipeline

下载 YouTube 音频并转写，调用 AI 生成分析报告，然后推送到 Telegram 并归档。

## 按频道配置内容类型

在 `config.json` 的 `youtube_channels` 中为每个频道设置 `content_type`：

| 值 | 处理范围 |
| --- | --- |
| `all`（默认） | 普通视频和已就绪的直播回放 |
| `video_only` | 仅普通视频，不包含直播回放 |
| `live_replay_only` | 仅已结束且回放已就绪的直播 |

例如，频道配置可以写为：

```json
{
  "youtube_channels": [
    {
      "url": "https://www.youtube.com/@channel_a",
      "name": "只看直播回放",
      "enabled": true,
      "content_type": "live_replay_only"
    },
    {
      "url": "https://www.youtube.com/@channel_b",
      "name": "只看普通视频",
      "enabled": true,
      "content_type": "video_only"
    }
  ]
}
```

此示例只展示频道部分；保留原有 Telegram 等配置。遗漏 `content_type` 等同于 `all`；无效值会在启动时直接报错。

### 筛选规则

- 通过 `yt-dlp` 读取 `/videos`、`/streams` 标签页，不依赖 RSS 的有限条目。
- 每个所需标签页最多检查最近 20 条，找到第一个类型匹配且可用的内容。`all` 比较两个标签页匹配项的发布时间，选最新一条；直播使用开播发布时间，不是结束时间。
- `not_live` 属于普通视频，`was_live` 属于已就绪回放。手动上传的直播录像若被 YouTube 标记为普通视频，也归入普通视频。
- 未开始（`is_upcoming`）、正在直播（`is_live`）、直播结束但回放尚在处理（`post_live`）均跳过，不更新处理状态，下轮重新检查。
- 查询失败或类型未知的候选不处理；不会放宽筛选条件来回退到其他类型。
- 不读取 Shorts 标签页，并额外排除带 Shorts 链接或 `#shorts` 标记的候选；不根据视频时长猜测类型。
- 已就绪内容的元数据使用进程内缓存，最多 512 条；未就绪状态和查询失败不缓存。重启程序会清空缓存。
- 单次模式和监听模式使用相同配置。配置在启动时读取，修改后需重启监听程序。

保留现有“每个频道每轮处理最新一条”的行为，不补抓全部历史内容；最近候选范围没有匹配项时正常跳过，不转写、不调用 AI，也不推送。

## 运行和测试

```bash
./venv/bin/python run_pipeline.py
./venv/bin/python run_pipeline.py --monitor --interval 1800
./venv/bin/python -m unittest discover -s test -v
```

测试使用模拟的 YouTube 元数据，不下载音频、不调用 AI、不发送 Telegram 消息。
