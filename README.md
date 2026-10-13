# 中文会议语音助手

Windows 本地中文会议转写桌面程序，使用 PySide6，支持三个可切换的识别引擎、时间戳、播放定位、文本编辑、说话人分离与导出。仓库名为 `chinese-speech-assistant`；应用保留现有桌面版本的名称和图标。

## 模型

| 选项 | 模型 | 设备与时间能力 |
|---|---|---|
| 轻量快转 | SenseVoiceSmall / sherpa-onnx INT8 | CPU；音频块区间与原生 token 起点，不是精确句子起止 |
| 高质量 A（默认） | Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B | CPU / NVIDIA CUDA；字词对齐 |
| 高质量 B | FireRedASR2-AED（第二代） | CPU / NVIDIA CUDA；自身 CTC 时间，失效时明确退回块时间 |

按需加载，每次任务使用独立进程；Qwen 识别结束释放 ASR 后再加载对齐器。详见[三模型接入说明](三模型接入说明.md)。

## Windows EXE 下载

[下载 v1.2.0 不含模型便携版](https://github.com/Zhanghaohao666/chinese-speech-assistant/releases/tag/v1.2.0)。下载两个 ZIP 分卷和 `merge-package.cmd`、`merge-package.ps1` 到同一目录，双击 CMD 校验合并，然后解压运行 `wwh专属语音助手.exe`。无需安装 Python；保留整个解压目录。模型通过“模型管理”中的官方链接自行下载。

## 从源码运行

1. 准备 Windows 10/11 x64 和 Python 3.12 x64。
2. 在仓库目录用 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

3. 双击 `启动.cmd`。
4. 在“模型管理”中点击官方下载链接，手动下载所需文件，解压后“选择本地目录”。也可用浏览器打开[模型下载指南](模型下载指南.html)。Qwen 需要同时下载 ASR 和对齐器；不必下载全部三种引擎。
5. 导入、拖入录音，或复制文件后按 Ctrl+V；选择识别引擎并开始转写。

安装脚本建立 `.venv`，先安装匹配的 PyTorch / torchaudio 2.7.1 CUDA 12.6 构建，再使用 `requirements-lock.txt` 约束安装依赖。此构建也支持 CPU，无需安装 CUDA Toolkit；GPU 仍需兼容的 NVIDIA 驱动。建议至少 16 GB 内存。SentencePiece 固定 0.2.0，避免已在 Windows 上复现的 0.2.1 原生崩溃。

模型权重、Python 运行环境、录音、转写结果、用户配置和 EXE 发行包均不在此仓库中。模型下载完成后可离线转写。

## 功能与限制

- Maximalism 彩色界面（v1.2.0）：珊瑚红、明黄、青绿、紫色，粗描边和叠层卡片；正文保持高对比白底。使用用户提供的蓝绿麦克风图标。
- 导入、播放/暂停、时间定位、搜索、历史记录与真实后台进度。
- 阅读版与字幕版分别编辑；阅读段落显示一次开始时间和持续时间，保留原始时间及来源。
- TXT / DOCX / PDF 导出阅读结构；SRT / VTT 导出字幕；JSON 保留项目数据。
- 可选说话人分离（额外下载两份 ONNX 模型），以匿名标签区分声音，不识别真实身份；新安装默认关闭。
- 模型结果及说话人归属需要回听核对；缺少有效时间数据时不会均分音频伪造精确时间。
- FireRed 尚未接入标点模型；会议摘要、实时录音和批量队列尚未实现。

## 验证

开发机 Windows 11 x64、Python 3.12.4、PySide6 6.9.2、PyTorch 2.7.1+cu126。同一段 42.12 秒中文录音，在独立便携环境实测：

| 引擎 | 实际设备 | 耗时 | 结果 |
|---|---|---:|---|
| SenseVoice | CPU INT8 | 6.44 秒（含可选说话人分析） | 成功 |
| FireRedASR2-AED | GPU BF16 | 23.38 秒 | 成功 |
| Qwen ASR + 对齐器 | GPU BF16 | 33.48 秒 | 成功 |

72 项回归测试和 8 个子测试通过；导入、播放、编辑、六种导出、取消与失败恢复通过。详见 [v1.2.0 发布验证](docs/v1.2.0-validation.md)。

这不是识别准确率或跨电脑性能承诺。已验证含中文及空格的迁移目录、独立 Python 路径、缺少模型时的引导；尚未在另一台实体电脑实测。

运行不需要模型权重的回归测试：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

## 代码结构

- `src/transcriber/`：界面、后台任务、三模型实现、时间与阅读结构、导出、说话人处理。
- `src/transcriber/vendor/`：保留来源和许可证的 pyVideoTrans 分段及 FireRed AED 子集。
- `scripts/`：转写、恢复、阅读版导出和说话人处理 CLI。
- `tests/`：单元与界面回归测试。
- `packaging/`：Windows 原生启动器源码、图标、编译命令和模型链接清单。

`packaging/重建启动器.cmd` 只生成 EXE 启动器；便携发行还需准备独立 CPython 3.12 x64 及匹配依赖，放入 `runtime/`。它不是完整运行环境打包脚本，生成的 EXE 不能单独运行。

## 许可证

项目按 [GPL-3.0](LICENSE) 提供；第三方代码、组件和模型各自遵循对应许可，见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。模型权重由官方渠道另行下载。FireRed 源码子集保留 Apache-2.0 许可与修改记录；SenseVoice 模型许可不能等同于 sherpa-onnx 的代码许可。
