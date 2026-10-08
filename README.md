# YouTube News Pipeline

下载 YouTube 音频并转写，调用 AI 生成分析报告，然后推送到 Telegram 并归档。

## 当前工作目录

流水线始终以**启动命令时的当前工作目录**为基准，不使用固定用户路径，也不会切换到脚本所在目录：

| 用途 | 当前工作目录下的路径 |
| --- | --- |
| 配置 | `config.json` |
| 转写 | `transcript.txt` |
| 待发送分析报告 | `reports/主题名称.md`（AI 根据内容命名） |
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

## 报告生成、发送与归档

报告不再固定为 `analysis_result.md`。AI 根据内容命名，例如：

```text
reports/美债收益率上升与比特币机构配置.md
```

- 生成中的报告先写入 `reports/.pending/<任务标识>/`；程序确认本次只有一份非空 Markdown 后，才发布到 `reports/` 顶层，避免发送半成品或误把旧报告当成新结果。失败的暂存文件保留供排查，不进入发送队列。
- 每次流水线进入推送步骤，发送任务都会扫描 `reports/` 顶层的全部非隐藏 `.md` 文件，逐份作为文件发送到 Telegram；不扫描子目录或符号链接。
- **发送成功后才归档并移出 `reports/`**，格式为 `archive/YYYYMMDD_原文件名.md`，日期取实际归档当天。例如 `archive/20261008_美债收益率上升与比特币机构配置.md`。
- 报告发布或归档时遇到同名文件，自动加 `_2`、`_3` 等后缀，不覆盖旧文件。
- 发送失败的文件留在 `reports/`，其余文件仍继续处理；任务返回失败。已确认发送但归档失败的报告记录发送状态，下次只重试归档，不重复发送。
- `--skip-push` 将报告留在 `reports/` 等待以后发送；`--skip-archive` 会保留已发送报告，正常后续发送任务根据 `reports/.sent.json` 跳过重复发送并归档。不要删除该状态文件，修改报告内容则视为需要重新发送。
- 转写稿仍按 `archive/transcript_YYYYMMDD_序号.txt` 保存，本次报告生成成功后即可保存转写，不依赖 Telegram 成功。
- 旧的根目录 `analysis_result.md` 和旧归档不自动移动、重命名或发送；如需发送旧报告，可自行复制到 `reports/`。

**单独启动发送任务**（无需转写、AI 分析或频道配置）：

```bash
./venv/bin/python telegram_push.py
```

此命令读取当前目录 `config.json`，发送 `reports/` 中的待发送报告并归档。也可传具体文件路径，仅发送该文件、不归档：

```bash
./venv/bin/python telegram_push.py 'reports/某个主题.md'
```

批量发送使用文件锁，防止两个发送任务同时重复处理队列。Telegram 成功响应前发生超时，或响应后写入发送状态前进程中断，可能导致重试时重复发送；无法保证远端严格恰好一次交付。

## 单独分析指定视频

在当前项目工作目录运行，可按视频 ID 或完整 URL 处理单个视频：

```bash
./venv/bin/python run_pipeline.py --video-id 9Nh3i0ZO-Jg --skip-push
./venv/bin/python run_pipeline.py 'https://www.youtube.com/watch?v=9Nh3i0ZO-Jg' --skip-push
```

- 执行下载、转写与联网分析；`--skip-push` 不发送 Telegram，报告留在 `reports/`。省略时发送全部待发送报告，成功后归档；`--skip-archive` 可额外跳过归档。
- 手动入口不会遍历配置中的频道，也不会读取或更新监听状态；仍需当前目录的 `config.json`，但不要求配置 `youtube_channels`。使用 `--skip-push` 时不需要 Telegram 凭据。
- 模型优先级为 `--ai-model` > 全局 `ai_model` > OpenCode 默认，不自动匹配频道级模型或内容类型。可通过 `--ai-model` 指定想使用的模型。
- 视频 ID 必须为 11 位；支持 `watch`、`youtu.be`、`live`、`embed` 和 `shorts` 链接形式，实际处理仍排除 Shorts、正在直播、预告和未就绪回放。
- URL 和 `--video-id` 不能同时指定，也不能与 `--monitor` 同时使用。直接传频道 URL 时，只解析并处理该频道最新可处理内容。
- 正常下载流程会把已获取的视频标题、URL 和发布时间传给 AI，避免只靠转写内容猜测视频背景。
- 转写仍写入当前目录的 `transcript.txt`，会替换同名文件；报告存入 `reports/` 并独立命名。不要与监听程序在同一目录同时分析，以免转写互相覆盖。
- `--skip-transcribe` 会使用当前目录已有的转写稿，不重新下载或获取标题、发布时间；使用者须确认转写稿对应指定视频，程序不会验证其归属。

## 运行和测试

```bash
./venv/bin/python run_pipeline.py
./venv/bin/python run_pipeline.py --monitor --interval 1800
./venv/bin/python -m unittest discover -s test -v
```

测试使用模拟的 YouTube 元数据和 OpenCode 调用，不下载音频、不调用 AI、不发送 Telegram 消息。
