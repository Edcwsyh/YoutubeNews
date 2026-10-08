# YouTube News Pipeline

下载 YouTube 音频并转写，调用 AI 生成分析报告，然后推送到 Telegram 并归档。

## 当前工作目录

流水线始终以**启动命令时的当前工作目录**为基准，不使用固定用户路径，也不会切换到脚本所在目录：

| 用途 | 当前工作目录下的路径 |
| --- | --- |
| 配置 | `config.json` |
| 转写与分析报告 | `transcript.txt`、`analysis_result.md` |
| 归档 | `archive/` |
| 日志与监听状态 | `pipeline.log`、`.pipeline_state.json` |
| 音频临时目录 | `tmp/yt_transcribe/`（可用 `--work-dir` 覆盖） |

OpenCode 的分析和 session 清理也在该工作目录运行。分析 prompt 明确指定当前目录中的输入输出，skill 不会把路径解析到自己的目录。

运行前请确认当前目录有配置文件和 `.opencode/skills/newsanalysis/SKILL.md`（或已通过 OpenCode 的配置提供该 skill）。从其他目录用绝对路径调用脚本时，仍读取和写入调用者当前目录，不向脚本目录回退。

修改后重启 Python 监听程序。原先 `/home/Edcwsyh/work` 下的转写与报告不会自动移动；`--skip-transcribe` 需要当前目录已存在 `transcript.txt`。音频临时目录会被清理，请使用专用目录，不能指定为当前工作目录或其父目录。

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

## 配置 AI 分析模型

在 `config.json` 顶层设置 `ai_model`，也可以在单个频道中覆盖：

```json
{
  "ai_model": "provider/default-model",
  "youtube_channels": [
    {
      "url": "https://www.youtube.com/@channel_a",
      "content_type": "live_replay_only",
      "ai_model": "provider/other-model#variant"
    },
    {
      "url": "https://www.youtube.com/@channel_b",
      "content_type": "video_only"
    }
  ]
}
```

模型名称是占位符，请通过 `opencode models` 查看可用模型并替换；推理变体为可选的 `#variant` 后缀。保留原有 Telegram 等配置。

优先级：**命令行 `--ai-model` > 频道 `ai_model` > 全局 `ai_model` > OpenCode 默认模型**。

```bash
./venv/bin/python run_pipeline.py --monitor --ai-model 'provider/model#variant'
```

- 未配置或设置为 `null` 时继承下一层；各层均未配置时不传 `--model`，沿用 OpenCode 默认行为。
- 空字符串、非字符串或格式错误会在处理前报错。只校验按优先级实际选用的值，被覆盖的配置不生效。
- 模型可用性及认证由 OpenCode 检查；调用失败遵循原有重试逻辑，不自动切换模型。
- 日志会记录所选模型，首次调用和重试始终使用相同的模型参数和 session；成功后仍清理 session。
- 现有 `--model` 仍用于 Whisper 音频转写，与新增的 `--ai-model` 无关。不需要修改 OpenCode 的全局配置。
- 修改配置后需重启监听程序。未设置模型时不会改变现有调用行为。

## 运行和测试

```bash
./venv/bin/python run_pipeline.py
./venv/bin/python run_pipeline.py --monitor --interval 1800
./venv/bin/python -m unittest discover -s test -v
```

测试使用模拟的 YouTube 元数据和 OpenCode 调用，不下载音频、不调用 AI、不发送 Telegram 消息。
