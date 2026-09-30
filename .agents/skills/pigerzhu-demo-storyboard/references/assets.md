# 固定背景与素材说明

## 已保存的固定背景

- 文件：`../assets/newsprint-blue-gray.png`
- 尺寸：1920 × 1080，RGB，不透明纸张底；不是需要透明的独立插画。
- SHA-256：`d6045912d771385d7091e07912a163932148c7b9b0076781dec37b7128180cac`
- 制作日期：2026-09-26。来源：本次内置 imagegen 原创生成，无用户私有参考素材。不是扫描的真实报纸，不含任何品牌或文字。
- 模型原始输出为 1672 × 941；保存前仅用 FFmpeg Lanczos 统一为 1920 × 1080，一次性尺寸规范化，无调色。此文件是后续复用的唯一固定成品，不依赖生成工具缓存。
- 色彩目标 #C9DCE5；实际 RGB 均值约 (194.50, 212.11, 220.71)，纹理使像素不等于纯色。每通道标准差约 (6.08, 5.64, 4.80)。视觉基调为浅蓝灰，纸纤维与微小颗粒均匀分布。
- 实际查看了 1920 × 1080 成品：无文字、重折痕或明显暗角，保留细微纸纤维和磨损。它是纹理背景，不含分镜内容。

生成提示词（内置 imagegen 模式）：

> Create a single blank background asset for reusable editorial storyboard pages. Landscape 16:9, exactly 1920x1080 pixels if supported. Full-bleed uniform very light blue-gray newsprint paper, base color #C9DCE5. Subtle low-contrast paper fibers, extremely slight wear and fine printing grain evenly distributed. Flat scanned paper texture, neutral even illumination, no perspective. No text, lettering, symbols, illustrations, objects, heavy folds, torn edges, borders, shadows, or visible vignette. It must remain quiet enough for dark typography placed later. This is ONLY the blank background, not a finished storyboard page.

将固定成品字节一致复制到每次版本素材目录，记录哈希；所有静态设计页在 (0,0) 原尺寸引用，不重新生成、逐页调色或叠滤镜。实拍页按视频例外自然原色满屏，不引用纸张。用户明确变更视觉参数时另存项目级背景，旧版保留。

## 可复用样式与字体

`../assets/style.json` 为尺寸、颜色、字体偏好与字号起点；`../assets/style.css` 为排版基础类，不规定页面构图，也不画假黄底框或固定方框模板。

创建技能时本机检查结果：

| 角色 | 首选 | 已核实可用替代 | 文件 |
|---|---|---|---|
| 中文标题 | Songti SC 粗体 | Source Han Serif SC / Heavy | `C:/Windows/Fonts/Source Han Serif SC Heavy (TrueType).ttf` |
| 中文正文 | PingFang SC | Noto Sans SC / Regular | `C:/Windows/Fonts/Noto Sans SC (TrueType).otf` |
| 英文和大数字 | Georgia | Georgia / Regular | `C:/Windows/Fonts/georgia.ttf` |

名称通过字体实际元数据核实，不只按文件名猜。Songti SC/PingFang SC 未在本轮检查的 Windows 系统/用户字体目录发现。标题使用 Heavy 对应粗宋；正文不要误用 Noto 变体字体的 Thin 默认实例。此表是本机记录，不是跨机器保证；每次制作重新确认最终字体、字重、字形覆盖和渲染结果。字体未复制进技能，跨机器需找到可用对应字体或按授权安装，记录真实替代；无须为了使用技能先安装 macOS 字体。

## 每期素材清单

由代理维护，不要求用户补表。记录每项语义用途、本地有效路径、来源 URL 或生成说明、获取日期、哈希、可编辑/光栅属性、许可/已知使用限制；不知道的限制写未核实，不编造。

真实 Logo、书封、人物身份和界面须核实来源，缺失就指出；不得生成冒牌替身。插画按同组风格制作，检查真实透明 alpha 及深浅底边缘。文字/数字/公式/箭头用确定性排版，背景/卡片/线/强调/笔刷各层可编辑。源文件用语义组连接相关图和短标签。

每个版本的《分镜说明.md》链接实际素材说明和字体记录，不能只链接本技能的默认表。正式分镜的素材、页数、台词、金额、时间戳不写回本技能。

## 实际获取与检查

- 图标：按语义选择同一免费系列的具体图标，保存原 SVG、来源地址和许可原件。核对商业/修改范围及署名要求，记录改色、缩放等修改；许可要求保留版权声明时随源交付。不能用 emoji 或临时拼接形状充数。
- 插画：调用可用图像生成工具生成独立透明素材，保存提示词、日期、原始输出、最终引用路径。人物动作与道具服务当前内容，物件组风格一致；不生成文字、数值、图表、公式或关系箭头。验证 alpha 极值、透明比例、可见包围盒，并在纸底、深底、棋盘底目视检查；有白框或伪透明就修正后再用。裁掉多余透明留白时保留原始资产，记录处理。
- 实拍：对适合的人物处境实际搜索并打开具体素材，观看视频、核实单项许可和人物使用限制，而非仅收藏搜索页。保存合法下载的视频文件、来源页、作者、许可地址/获取日期/本地证据及哈希。不能凭站点“免费”字样推定每条素材都可商用。
- 实拍片段时长用 FFprobe 实测，选区以 1 倍速完整覆盖音频镜区间；不以页面四舍五入时长推定足够。保存素材内起止毫秒、源音频绝对起止毫秒、速度、静音、裁切/缩放、代表帧时间。禁止定格、循环、倒放或减速凑时长。若不足、许可不清、下载不可用或画面不贴合，记录具体原因并制作对应场景插画替代。
- 真实人物不能被描述为用户本人或真实投资者持仓，不能暗示品牌/演员背书；真实视频中的界面仅作情境素材，不当作本例行情或操作教学。来源限制不明确时不捏造授权证明。

建议版本内按 `assets/icons`、`assets/illustrations`、`assets/video` 分开保存；所有被选中资产须在交付源中实际引用。素材清单列出已落实与缺项，整页 SVG、流程框、数据格不计作叙事插画。
