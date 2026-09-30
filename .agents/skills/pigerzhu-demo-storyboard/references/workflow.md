# 工作流与辅助脚本

## 读取顺序与运行条件

先读音频与完整 SRT，再形成有语义的镜头分组。脚本不做“按句分镜”，不猜时间，不需要用户补 JSON。`plan.json`、`inspection.json` 是代理内部工作文件，代理自行生成并维护；用户只提供配套音频/SRT和自然语言反馈。

Python 3 标准库即可运行 `scripts/storyboard.py`。音频时长由 FFprobe 实测，不用字幕末尾当作音频时长。可从 PATH 找 FFprobe/FFmpeg，或显式传绝对路径。若项目使用 Remotion，可定位其已安装 compositor 包内的 ffprobe.exe / ffmpeg.exe；不要将某台电脑路径写进脚本。缺失时报告并按用户授权安装，不静默猜测。

## 每次新版本

选择尚不存在的绝对目录 `outputs/<项目>/v001`（已有就递增）。运行：

```text
python <skill>/scripts/storyboard.py inspect --audio <绝对音频路径> --srt <绝对字幕路径> --out <新版本目录> --ffprobe <FFprobe路径>
```

默认 UTF-8/BOM，遇解码错误先识别编码，再显式 `--encoding gb18030` 等，绝不用丢弃错误字符的解码。脚本保留所有字幕文字、行内空格、标点与标签；只在内存统一换行，原 SRT 字节不变。空字幕、格式坏块不静默跳过。重复编号保留并报告，用从 1 开始的 cue 顺序号分配镜头。

生成 `inputs/audio.<原扩展名>`、`inputs/srt.srt` 和 `inspection.json`，包含原路径、同版副本、SHA-256、实测时长、全部字幕和定位冲突。时间统一整数毫秒，展示 `HH:MM:SS.mmm`，均为源音频绝对时间。

通读所有 cue 后由代理编写 `plan.json`。内部结构如下（占位解释，不是要用户填的表，也不是固定分镜例子）：

```text
version: 版本标识
listening_review: 首尾及各切点实际听查结果、工具、位置；未听查直说
shots: 按源顺序的镜列表，每镜包含：
  id: 唯一镜编号
  cues: 连续 cue 顺序号的整数数组
  start_ms, end_ms: 源音频绝对起止（整数毫秒）
  meaning: 本镜对象、动作、关系、语义分组依据
  visual: 主画面与 1–2 种主要视觉手法
  screen_text: 精简上屏字（无则写“无”）
  opening: 开场先看什么（禁止提前揭示后文结论）
  develop: 之后按什么顺序增加什么、最后完成态
  retain: 从前镜/状态保留什么、共享坐标/比例（无则写“无”）
  transition: 下一镜如何衔接、如何处理相邻字幕间隙/停顿
  media_decision: 对象/动作/变化/关系、主媒介、具体素材、选择理由
  media_kind: design 或 video
```

不在 plan 重抄原文；导出器自动从源字幕填入，避免误改。整个分配数组必须恰好为所有 cue 各一次、顺序一致；镜间区间连续，覆盖音频从 0 到真实末尾。首尾无字幕部分可保留画面，在脚本注明；并不意味着要凭空添加口播。切点可置于两条字幕之间的停顿，经听查后选；不得穿过字幕或裁掉完整词句。字幕自身冲突不能擅改源文件，应在完整脚本注明具体 cue/时间和处理建议，等用户澄清源数据后另存版本。

需要定位听查片段时运行（只输出衍生 WAV，不改源）：

```text
python <skill>/scripts/storyboard.py audition --inspection <版本>/inspection.json --plan <版本>/plan.json --ffmpeg <FFmpeg路径>
```

输出开头、结尾、每个切点前后约 1.5 秒的 WAV 和源区间索引。实际试听它们，必要时扩大到完整句子并听全片，核对字幕与音频内容一致。仅生成片段不算听查。如果工具无法听取，注明未核验的位置，请用户确认必要冲突，不谎报通过。

## 第一次交付与确认

```text
python <skill>/scripts/storyboard.py export --inspection <版本>/inspection.json --plan <版本>/plan.json --phase script
```

输出完整《分镜脚本.md》，包含所有镜、所有原文、自动覆盖、实测时间和定位问题。时间错误可带定位输出供讨论；漏 cue、重复 cue、错序等无法完整保真时直接报错，先修内部分配。该阶段只向用户交脚本，不制作分镜 PNG；内部 plan 不要推给用户填。

等用户确认这版完整脚本后，代理记录实际确认消息（不能自行编造）：

```text
python <skill>/scripts/storyboard.py approve --inspection <版本>/inspection.json --plan <版本>/plan.json --evidence <用户确认原话及消息定位>
```

自动脚本能约束“确认对应哪版”，不能证明用户真的说过；必须依会话证据调用。脚本、语义计划或源版本改变后旧确认失效。approve 不会通过未解决的时间错误。修订总是新目录重新 inspect 并迁移必要文件，重新生成完整脚本；直接改原 SRT 不被允许。纯排版局部修订可沿用相同语义的确认依据，但需在新版本导出同内容脚本后重新绑定，并注明此前批准的版本；不可伪装成新的用户消息。

用户明确授权直接按指定方向重设计时，按该授权在新版本更新视觉字段、导出可追溯修订脚本并绑定实际授权消息，随后直接制作；无需再次索取形式上的确认。保持原文、cue 分配和边界，除非用户同时授权更改；确需改动时指出具体冲突。

## 图片完成后的内部补充字段

代理完成所有页、各可编辑层、所有引用资源和目视检查后，在 plan 增补下列字段，不改变已确认的语义字段：

```text
canvas: [1920,1080]，只有用户明确覆盖默认值时才改
font_report: 实际字体/字重/文件/许可或可用性记录 Markdown 的绝对路径
asset_report: 素材源、生成方式、URL/日期/许可、哈希/透明检查的 Markdown 路径
visual_review: 逐页原尺寸、阶段、联看检查记录 Markdown 路径
sequence_review: 实际全片联看观察
每镜新增：
  png: 完成态 PNG 绝对路径
  editable: 可编辑源入口绝对路径（SVG、HTML、源项目等）
  assets: 本镜背景、独立插画、笔刷等非空有效绝对路径数组
  stages: [{kind: opening/reveal/complete, state: 可复现状态入口或参数, png: 截图绝对路径, observation: 实际检查观察}, ...]
  review: 本页实际验收观察与修正
  video: 仅 media_kind=video 时必填
    file: 本地视频绝对路径
    source_url, license_url, credit: 来源、许可、作者
    license_record: 本地许可/限制记录绝对路径
    duration_ms: FFprobe 实测可用视频流时长
    in_ms, out_ms: 素材内连续选区
    audio_start_ms, audio_end_ms: 对应源音频绝对区间
    speed: 1
    mute: true
    crop: 可复现缩放与裁切规则
    representative_frame: 实际提取的代表帧绝对路径
    representative_ms: 代表帧的素材内时间
```

阶段至少有 opening、complete，逐步展开时还包含全部关键新增状态；静态相同画面可复用一张截图但说明原因。报告内记录源的全部依赖；源用相对路径可方便迁移，说明用有效绝对路径供用户点击。透明插画检查不能仅靠后缀。

```text
python <skill>/scripts/storyboard.py export --inspection <版本>/inspection.json --plan <版本>/plan.json --phase final
```

生成《分镜说明.md》。脚本检查路径存在非空、PNG 签名/尺寸、同版输入哈希、确认指纹与覆盖。它不渲染或判断语义/视觉，也无法证明 SVG 没有扁平化；代理必须实际验收。它不会覆盖已有文档，改稿进入新版本。字幕标签会在文档原文区按字面显示，不被解释为命令或 HTML。

最终交付还包含总览、媒介选择与视觉修订依据、独立素材及来源许可、完整可编辑依赖、视频区间映射（含未选用候选与排除理由）。视频镜以代表帧交 PNG，以本地视频和区间映射交动态来源；不要把代表帧当作将来的定格片段。仅分镜任务不擅自渲染完整 MP4。

## 验证

`python <skill>/scripts/test_storyboard.py --ffprobe <路径> --ffmpeg <路径> --work <工作目录>` 使用合成 WAV/SRT 测试，不读取用户私有素材；检查逐字保真、覆盖、重复/丢失/错序、时间越界/重叠/切点、源哈希、批准版本、导出路径与完整文档。图像测试只为文件格式验证，不是正式分镜。
