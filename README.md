# pigerzhu 视频制作 Skills

两个配合使用的 Codex Skill：从定稿口播和 SRT 规划分镜，再将确认后的分镜制作成分层动画。

| Skill | 输入 | 交付 |
| --- | --- | --- |
| `pigerzhu-demo-storyboard` · pigerzhu 演示分镜图生成 | 配套音频与完整 SRT | 先交完整分镜脚本；确认后制作 PNG、可编辑源、素材及分镜说明 |
| `pigerzhu-demo-mp4` · pigerzhu 演示 MP4 动画生成 | 已确认的完整《分镜说明.md》及其引用文件 | 分层动画 MP4、可编辑源、绝对时间映射与检查报告 |

## 使用

把 `.agents/skills/` 中的两个完整文件夹复制到你的项目 `.agents/skills/` 下，再在该项目中使用 Codex。需要跨项目使用时，可放入个人技能目录 `~/.agents/skills/`。不需要复制本仓库以外的旧项目。

```text
$pigerzhu-demo-storyboard
根据提供的音频和 SRT 制作分镜。先交完整脚本，等我确认后再生成图片。
```

确认脚本、生成并审阅分镜后：

```text
$pigerzhu-demo-mp4
按这份已确认的完整《分镜说明.md》制作全片，保持原配音和定稿布局，另存新版本。
```

MP4 Skill 可指定源音频绝对区间，例如“只制作 00:30–00:45”；不指定则制作全片。说明中的音频、SRT、PNG、可编辑源与素材必须真实存在，不是只提供一个缺少关联文件的 Markdown。无需用户填写 JSON 或图层时间表。

## 依赖与边界

- 基础脚本：Python 3、FFmpeg / FFprobe。
- 动画渲染：Node.js、Playwright、可用的 Chromium / Chrome。脚本支持指定浏览器路径；可选环境变量为 `PIGERZHU_CHROME`。
- 生成插画、查找素材等步骤需要执行环境提供相应工具与访问能力；Skill 本身不附带账号、密钥或服务额度。
- 默认 1920×1080、30 fps、H.264/yuv420p、原配音 AAC；不自动添加音乐、新配音或整条字幕。
- 静态设计默认复用随 Skill 保存的浅蓝灰新闻纸；实拍按分镜说明处理。不固定主题、镜数、金额或台词。
- 技术检查、抽帧与脚本测试不等于实际视听验收；制作完成后仍需正常播放检查节奏和音画关系。

本仓库只包含 Skill 规则、脚本、通用样式与约 3.2 MiB 的固定背景，不包含示例配音、字幕、成片、个人素材、字体文件、缓存、凭证或旧项目。新的品牌调用名为 `pigerzhu-*`，旧 `nico-*` 名称不再作为本仓库入口。

## 自检

```text
python .agents/skills/pigerzhu-demo-storyboard/scripts/test_storyboard.py
python .agents/skills/pigerzhu-demo-mp4/scripts/test_parser.py
node .agents/skills/pigerzhu-demo-mp4/scripts/test_renderer.cjs <Chrome路径>
```

素材另有来源或许可时，按其各自许可使用；公开仓库不自动授予第三方素材使用权。
