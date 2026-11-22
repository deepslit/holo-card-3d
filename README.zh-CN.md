# `holo-card-3d` · 3D 全息流麻收藏卡技能 (v2.2)

**[English](README.md)** | **简体中文**

把任意角色立绘或参考图制作成 **3D 全息流麻（流动闪粉）SAR/UR 收藏卡**：内置 11+3 视角视差浮雕映射、金属倒角立体边框、可选像素级道具扫光（`prop_fx`）与解析场 SDF 飘落粒子（`motion_motif`），一次导出离线 **`60 fps` WebGL2 交互 HTML**、**`~16.7 fps` 零残影透明 WebP** 与 **`~16.7 fps` 棚拍背景 GIF** 三件套。

遵循开放的 **`SKILL.md` 标准**，同时提供独立 CLI 管线 —— 兼容**所有主流智能体 Harness 与编程 CLI**（Claude Code、Codex、Antigravity、Cursor、Windsurf、Gemini CLI、OpenCode、Cline、GitHub Copilot、Trae 等）。

<p align="center">
  <img src="docs/demo_saintess.gif" width="300" alt="Deep-Sea Saintess · 法杖扫光与星羽飘落" />
  &nbsp;&nbsp;&nbsp;
  <img src="docs/demo_neko.gif" width="300" alt="Neko Y2K · 棱镜滑板扫光与赛博星屑" />
</p>

---

## ⚡ 最快上手：直接把这句话发给你的智能体

不需要手动配环境或敲命令——把参考图连同下面这句话，直接发给**任意支持技能或命令行的智能体**：

```text
帮我下载并安装技能 https://gitee.com/deepslit/holo-card-3d，然后用它把这张图做成 3D 流麻闪卡
```

> - **GitHub 主仓库地址**：`https://github.com/deepslit/holo-card-3d`（两个地址代码实时自动同步，国内推荐用 Gitee 镜像更快）
> - **已经安装过技能？** 后续直接发图并说：`用 holo-card-3d 把这张图做成 3D 流麻闪卡` 即可。

---

## 核心亮点 (`v2.2`)

- **三路线意图优先（支持零 AI 生图直出）**：
  - **路线 1（零生图 — 保留原图像素）**：只需放入一张图到 `01_raw_layers/mid.*`（支持原生透明 RGBA、绿/洋红/蓝幕、纯色棚拍背景或 GrabCut 局部抠图）→ 本地自动抠图 + 程序化氛围背景 + 内置 `1200×1600` 收藏卡框 + 自动视差深度图。
  - **路线 2（混合路线）**：保留原图角色像素，仅替换背景/边框（或反过来）。
  - **路线 3（AI 重绘）**：调用内置生图工具或使用 `references/prompt-templates.md` 提示词模板进行风格化重构与 TCG 重绘。
- **渲染前资产体检（Asset Lint）与 3 秒快速预览门控**：
  - `prepare_assets.py` 自动检查宽高比不匹配（配合 `mid_fit: "auto"` 智能安全构图）、边缘裁切（耳朵/武器顶边）、抠图色边污染以及边框过挤。
  - `--stage preview` 仅需约 3 秒即可渲染 `03_processed/preview_composite.png`（正视图 + 倾斜全息流麻图 + 透明棋盘格），先确认构图和卡面文字，再跑完整 84 帧动画编码。
- **可控卡面文字模式（`label_mode`）**：支持 `"page_only"` *(干净纯图卡面 + HTML 页面 HUD)*、`"on_card"` *(金属铭牌直接精雕进卡面，HTML / WebP / GIF 三端同步展示)* 或 `"hidden"`。
- **可选「1+1」局部点睛特效（零额外 AI 生图成本）**：
  1. **像素级道具扫光（`prop_fx`）**：通过 `0.05` UV 网格标尺（`--stage prop-grid`）+ 自动排除手部的多边形遮罩（`prop_mask.png`），实现单束定向高光扫过与发丝级星芒。
  2. **解析场 SDF 飘落动态（`motion_motif`）**：支持面部安全区避让的双层景深粒子（`feathers_bubbles`、`cyber_stars`、`petals`、`embers`、`snowflakes` 或 `none`）。
- **标准化三件套交付（`<workdir>/output/`）**：
  - `holographic_card.html` — 单文件离线 **`60 fps`** WebGL2 交互卡（`5.2s` 自动巡航、`±30°/±19°` 拖拽与陀螺仪、`流畅`/`高清` 切换、3 种棚拍模式）。
  - `holographic_card.webp` — `690×960` 透明通道动态 WebP（**`84 帧 @ 60ms` ≈ `16.7 fps`, `5.04s`**，`dispose=1, no_blend=1` 零残影）。
  - `holographic_card.gif` — `460×640` 主题棚拍背景 GIF（**`84 帧 @ 60ms` ≈ `16.7 fps`, `5.04s`**，共享 256 色 Median Cut + Floyd–Steinberg 抖动）。

---

## 手动安装与环境自检

### 1. 检查 Python 环境并安装依赖
```bash
# 纯标准库预检（自动识别 Windows Store 占位 python、版本、依赖包、磁盘与内存）
python scripts/check_env.py

# 安装已验证兼容版本的依赖
pip install -r requirements.txt
```

### 2. 手动安装到智能体技能目录（通用任意 Harness）
`holo-card-3d` 基于开放的 [`SKILL.md`](SKILL.md) 规范编写，无任何私有绑定，支持所有可读取 `SKILL.md` 或可执行命令行的智能体 Harness：

```bash
# 通用跨智能体项目技能目录（Antigravity、Codex、Gemini CLI、OpenCode、Copilot 等）
git clone https://gitee.com/deepslit/holo-card-3d.git .agents/skills/holo-card-3d

# 或各工具全局技能目录示例：
git clone https://gitee.com/deepslit/holo-card-3d.git ~/.claude/skills/holo-card-3d   # Claude Code
git clone https://gitee.com/deepslit/holo-card-3d.git ~/.codex/skills/holo-card-3d    # Codex
git clone https://gitee.com/deepslit/holo-card-3d.git ~/.cursor/skills/holo-card-3d   # Cursor
```

> **兜底用法**：即使你的智能体工具不支持自动扫描 `skills` 目录，也可以把仓库克隆到任意位置，直接让它「阅读 `SKILL.md` 并调用 `scripts/run_pipeline.py`」。

---

## 独立 CLI 管线用法

```bash
# 0. 验证 Python 解释器与依赖
python scripts/check_env.py --workdir ./my_card

# 1. 本地像素级抠图（支持 RGBA / 绿洋红蓝幕 / 纯色棚拍 / GrabCut）
python scripts/run_pipeline.py --workdir ./my_card --stage matte

# 2. 对齐与深度生成、程序化背景（未提供 bg 时）、资产体检与遮罩生成
python scripts/run_pipeline.py --workdir ./my_card --stage prepare

# 3. 约 3 秒快速双角度预览（全量渲染前先检查 03_processed/preview_composite.png）
python scripts/run_pipeline.py --workdir ./my_card --stage preview

# 4. （可选）导出 0.05 UV 网格坐标图，用于标定 card_config.json 中的 prop_fx 多边形
python scripts/run_pipeline.py --workdir ./my_card --stage prop-grid

# 5. 生成 60fps HTML + 渲染 84 帧 (~16.7fps) WebP/GIF + 技术指标校验
python scripts/run_pipeline.py --workdir ./my_card --stage html
python scripts/run_pipeline.py --workdir ./my_card --stage render
python scripts/run_pipeline.py --workdir ./my_card --stage verify
```

准备好 `card_config.json` 与 `01_raw_layers/` 后，也可以一条命令跑完全流程：
```bash
python scripts/run_pipeline.py --workdir ./my_card --stage all
```

---

## 仓库目录结构

```text
holo-card-3d/
├── SKILL.md                  # 跨 Harness 通用智能体指令 (v2.2)
├── README.md                 # 英文说明文档
├── README.zh-CN.md           # 中文说明文档
├── requirements.txt          # Python 依赖版本约束
├── LICENSE                   # MIT 开源协议
├── agents/openai.yaml        # 可选 Codex UI 元数据
├── assets/
│   ├── card_config.example.json
│   ├── palettes.json
│   └── frames/               # 内置 1200x1600 RGBA 收藏卡边框
├── docs/                     # README 演示动图
├── references/
│   ├── prompt-templates.md   # 路线 2/3 分层生图提示词模板
│   └── standard-spec.md      # 光学、动态、Asset Lint 与 QA 规范
└── scripts/
    ├── check_env.py          # 跨平台解释器、依赖、磁盘与内存预检
    ├── run_pipeline.py
    ├── matte_layers.py       # RGBA / 色键 / 纯色 / GrabCut 本地像素抠图
    ├── build_prop_mask.py
    ├── prepare_assets.py     # 智能构图、程序化背景、卡面铭牌、资产体检
    ├── build_html_card.py
    ├── render_card.py        # 3 秒快速预览与 84 帧 WebP/GIF 渲染器
    └── verify_outputs.py     # 客观技术校验 + 视觉 QA 检查单
```

---

## 开源协议

[MIT](LICENSE)
