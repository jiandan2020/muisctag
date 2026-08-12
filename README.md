# MusicTag — 全格式音频标签批量编辑与刮削整理工具

MusicTag 是一款基于 Python + PySide6 + mutagen 的 Windows 桌面工具，用于音频元数据
（ID3 标签）的批量读取/编辑、在线刮削、歌词获取与文件整理修复。

## 功能特性

### 1. 元数据批量编辑
- 支持格式：**MP3、FLAC、APE、WAV、AIFF、WV、TTA、M4A、MP4、OGG、MPC、OPUS、WMA、DSF**
- 统一字段：标题、专辑、艺术家（多值）、专辑艺术家、作曲者、编曲者、作词者、
  曲目/总曲数、碟片/总碟数、年份、流派、时长、歌词、封面、ISRC、版权、出版商、
  注释、BPM、编码者
- 多选文件批量修改同一字段（可配置“清空未填写字段”）
- 从文件名/文件夹结构自动推断标签（`艺术家 - 歌名`、`03 艺术家 - 歌名`、`专辑/CD2/05 歌名` 等）
- ID3v2.3 ↔ ID3v2.4 ↔ ID3v1 版本互转
- 标签清理：去空格、零宽字符、Unicode NFC、统一 `Feat.` 写法、英文标题大小写、
  繁简转换（可选安装 opencc）
- 修改前自动备份原始标签到 `%APPDATA%\MusicTag\backups`

### 2. 在线刮削（插件化）
- 平台插件：网易云音乐、QQ音乐、酷狗音乐、Lrclib、Apple Music、Musixmatch（需 Key）
- 多平台并发搜索、合并去重、结果列表供选择
- 自动补全缺失的标题/艺术家/专辑/年份/歌词/封面
- 参考 Lyrico-Plugins 的插件接口设计：每个平台实现 `search` / `get_lyrics` / `get_cover`
  三个能力即可接入新平台

### 3. 歌词
- 解析格式：LRC（逐行/逐字增强型）、YRC、QRC（QQ 加密解密）、KRC（酷狗加密解密）、
  SRT、ASS、TTML、纯文本
- 格式互转：LRC / SRT / ASS / TTML / 纯文本
- 整体时间轴平移、逐字时间戳保留
- 翻译：Google（免费）、Bing（网页接口）、OpenAI 兼容 API、MyMemory
- 原文 + 译文合并

### 4. 整理与修复
- 重复文件检测：音频指纹（首尾 SHA-1）+ 元数据相似度
- 自定义模板重命名/目录整理：`{artist}/{album}/{track2} {title}.{ext}`
- 缺失标签扫描并导出 TXT/CSV 报告

## 安装与运行

要求：Windows 10/11，Python 3.10+

```powershell
python -m pip install -r requirements.txt
python main.py
```

可选依赖（繁简转换）：
```powershell
python -m pip install opencc-python-reimplemented
```

## 项目结构

```
musictag/
├── main.py                     # 程序入口
├── requirements.txt            # 依赖清单
├── README.md
└── musictag/
    ├── core/                   # 核心业务
    │   ├── metadata.py         #   统一元数据抽象层（14 种格式读写/ID3 版本互转）
    │   ├── filename_parser.py  #   文件名/目录结构推断
    │   ├── tag_cleaner.py      #   标签清理与标准化
    │   ├── renamer.py          #   重命名模板引擎
    │   ├── dedup.py            #   重复文件检测
    │   └── report.py           #   缺失标签报告
    ├── lyrics/
    │   ├── model.py            #   歌词数据模型（行/逐字/元数据）
    │   ├── parser.py           #   LRC/YRC/QRC/KRC/SRT/ASS/TTML 解析与解密
    │   ├── converter.py        #   格式转换/时间平移/译文合并
    │   └── translator.py       #   Google/Bing/OpenAI/MyMemory 翻译
    ├── scrapers/               # 刮削插件体系
    │   ├── base.py             #   插件统一接口（search/get_lyrics/get_cover）
    │   ├── netease.py          #   网易云音乐
    │   ├── qq.py               #   QQ音乐
    │   ├── kugou.py            #   酷狗音乐
    │   ├── lrclib.py           #   Lrclib
    │   ├── apple.py            #   Apple Music / iTunes Search
    │   ├── musixmatch.py       #   Musixmatch（需 API Key）
    │   └── manager.py          #   聚合搜索/去重/批处理
    ├── gui/                    # PySide6 图形界面
    │   ├── main_window.py      #   主窗口（菜单/工具栏/三栏布局/任务调度）
    │   ├── file_panel.py       #   文件列表（拖拽/多选/勾选/右键）
    │   ├── metadata_panel.py   #   元数据编辑面板（分类 Tab/封面预览）
    │   ├── lyrics_panel.py     #   歌词编辑/转换/翻译面板
    │   ├── scrape_dialog.py    #   刮削搜索选择对话框
    │   ├── rename_dialog.py    #   重命名预览对话框
    │   ├── settings_dialog.py  #   设置对话框
    │   └── workers.py          #   后台任务线程（不卡界面）
    └── utils/
        ├── config.py           #   配置文件（%APPDATA%\MusicTag\config.json）
        └── network.py          #   UA 轮换/代理/重试请求封装
```

## 使用说明

1. **添加文件**：点击“添加文件/添加文件夹”，或直接把文件/文件夹拖入左侧列表。
   每个文件前有勾选框，批处理作用于“勾选”的文件；单文件编辑作用于“选中”的文件。
2. **编辑标签**：在中间面板修改字段 → 点“保存修改”。多选时相同字段显示公共值，
   未填写字段默认保留原值（可勾选“清空未填写的字段”）。
3. **从文件名推断**：选中文件后点“从文件名推断”，自动把 `艺术家 - 歌名` 等
   命名拆解填入空缺字段。
4. **自动刮削**：选中文件 → “工具 → 刮削选中歌曲”，在搜索结果中选一条 →
   “获取歌词/封面”预览 → “应用到选中文件”。
5. **批量刮削**：勾选多个文件 → “工具 → 批量自动刮削”，自动为每首歌搜索并补全
   歌词/封面/年份等缺失字段（后台线程，可看日志与进度）。
6. **歌词**：右侧面板可直接粘贴歌词；`打开歌词文件` 支持 LRC/SRT/ASS/TTML/QRC/KRC；
   “转换格式”在 LRC/SRT/ASS/TTML/纯文本间互转；“时间平移”整体调整时间轴；
   “翻译歌词”调用所选引擎（OpenAI 需先在设置中填 Key）。
7. **重命名/整理**：勾选文件 → “编辑 → 重命名/整理目录”，输入模板并预览后执行。
8. **去重/报告**：勾选文件 → “工具 → 检测重复文件 / 缺失标签报告”。
9. **设置**：网络代理与请求间隔、刮削偏好（ID3 版本/封面尺寸）、翻译引擎与 API Key。

## 配置说明

配置文件位于 `%APPDATA%\MusicTag\config.json`（首次运行自动生成），主要项：

| 键 | 说明 |
|----|------|
| `network.proxy` | HTTP(S) 代理，如 `http://127.0.0.1:7890` |
| `network.delay` | 请求间隔秒数，防反爬；被限流时可调大 |
| `scrape.id3_version` | 写入 MP3 时的 ID3 版本（v2.3 / v2.4 / v1） |
| `scrape.cover_size` | 封面尺寸 px（0 = 原图） |
| `translate.engine` | 默认翻译引擎 |
| `translate.openai_*` | OpenAI 兼容接口的 Base URL / Key / 模型 |

## 数据源与注意事项

- 各音乐平台接口均为公开/网页接口，可能随时变动或被限流；建议设置请求间隔、
  使用代理、批量刮削控制在合理规模。
- Lrclib 无需密钥；Musixmatch 需在设置中填入 API Key（申请自 Musixmatch 开发者后台）。
- Apple Music 歌词接口需要付费开发者令牌，本工具暂未接入歌词，仅提供封面与元数据。
- 大文件（DSF/WV 等）仅读写标签区块，不做整文件内存加载，可放心处理。
- 所有写操作前自动备份原标签 JSON 快照；如需恢复可到
  `%APPDATA%\MusicTag\backups\<时间戳>\` 查找。

## 扩展新平台

在 `musictag/scrapers/` 下新建模块，继承 `ScraperPlugin` 并实现三个方法：

```python
from .base import ScraperPlugin, TrackMatch, LyricResult

class MyPlugin(ScraperPlugin):
    name = "myplatform"
    display_name = "我的平台"
    def search(self, keyword, limit=10): ...      # -> List[TrackMatch]
    def get_lyrics(self, track): ...              # -> Optional[LyricResult]
    def get_cover(self, track): ...               # -> Optional[bytes]
```

然后在 `manager.py` 的 `PLUGIN_REGISTRY` 注册即可出现在刮削列表中。

## 常见问题

- **运行报缺少 PySide6**：执行 `python -m pip install PySide6 Pillow`。
- **刮削无结果**：检查网络/代理；平台接口可能已变更，可尝试调大请求间隔。
- **繁简转换无效**：需安装 `opencc-python-reimplemented`。
- **MP3 写入后版本不对**：在“设置 → 刮削 → MP3 ID3 版本”中选择目标版本。
