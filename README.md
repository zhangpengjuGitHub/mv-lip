# mv-lip

给**已经剪好的视频**里的人物，按音乐重新对口型。

不再用音频驱动生成整段视频（Wan2.2-S2V / InfiniteTalk 在 T4×2 上实测 17 秒要跑 2h20m，194 秒全曲 ≈ 26 小时，单会话跑不完）。改成：先剪画面 → 后期只改嘴 → 叠回原音轨。算力降到小时量级，全曲可行。

---

## 一、链路（四步，顺序不能变）

```
剪好的视频 cut.mp4（含音乐，25fps）
   │
   ├─ 抽出音轨 ── Demucs 分离 ──> vocal_dry.wav   ← 只作驱动信号，绝不当最终音轨
   │                                                │
   └────────────────────────── MuseTalk 1.5 对口型 ──┤
                                                      ▼
                              无声视频 lipsynced.mp4
                                    │
                     叠回原完整混音 song_final.wav
                                    ▼
                              final.mp4
```

**三个硬约束**

1. **必须喂干声。** 带伴奏/混响的音频直接喂进去，口型会明显漂移（两条独立实测）。但分离出来的人声又干又薄，**成片必须用原始完整混音**。
2. **音乐时间轴不要动。** 不裁剪、不变速、不做时间拉伸；从同一条音轨分出的干声与原混音天然同源同长，无需对齐校正。视频统一 **25 fps**（MuseTalk 训练帧率，也是 InfiniteTalk 的输出帧率）。
3. **只改嘴。** 表情、头部动作、身体、运镜全靠你剪进去的原始画面。静态图 + 水墨背景 = 一张会唱歌的照片。想要演唱感，先用 I2V 让人物有头部微动和呼吸，再对口型。

---

## 二、调研结论（GitHub API 实测，2026-11-03）

搜索「传入视频 + 音频 → 修改视频人物口型」，共筛出 9 个相关项目，**没有一个是专为唱歌做的** —— 全部面向说话/配音，唱歌需要实测。详见 [docs/选型对比.md](docs/选型对比.md)。

| 项目 | Stars | 许可 | 结论 |
|---|---|---|---|
| **TMElyralab/MuseTalk** | 6862 | 代码 MIT，权重官方声明可商用 | ✅ **本项目主选** |
| bytedance/LatentSync | 6238 | Apache-2.0（权重需自核） | 备选，画质更锐但扩散模型慢 |
| OpenTalker/video-retalking | 7299 | Apache-2.0 | 老项目（2022），画质一般 |
| Rudrabha/Wav2Lip | 13263 | 无明确许可，LRS2 数据禁商用 | ❌ 排除（但可作同步基准） |
| Zz-ww/SadTalker-Video-Lip-Sync | 2008 | — | 中文项目，带 GFPGAN + DAIN 插帧增强 |
| ShmuelRonen/ComfyUI-LatentSyncWrapper | 964 | — | ComfyUI 节点，可复用现有环境 |
| numz/sd-wav2lip-uhq | 1424 | Apache-2.0 | Wav2Lip 画质增强版 |
| primepake/wav2lip_288x288 | 652 | MIT | 288×288 改良版 |
| PaddlePaddle/PaddleGAN | 8044 | Apache-2.0 | 内含 Wav2Lip |

### 为什么选 MuseTalk 1.5

- **快**：不是扩散模型，在 VAE 潜空间做单步 inpainting，V100 上 30fps+；4GB 笔记本 fp16 跑 8 秒约 5 分钟。T4 上 194 秒全曲落在一个会话内。
- **可商用**：代码 MIT，README 明确「模型可用于任何目的，包括商业用途」（Wav2Lip 因 LRS2 数据严禁商用）。第三方组件 Whisper / DWPose / S3FD 各自保留原许可，商用前需自核。
- **输入正好是我们要的**：YAML 里填 `video_path`（视频 / 单图 / 图片目录都行）+ `audio_path`。
- **`bbox_shift` 能调嘴巴张开度**（正值增大、负值减小）—— 这是唱歌场景的关键旋钮，长音「啊——」的大开口靠它调。
- 官方推荐 25fps；低于 25fps 要插帧或转码。
- 官方建议先用 MuseV/I2V 生成有动作的视频再对口型，印证了「只改嘴」的局限。

**已知短板**：脸部裁剪只有 256×256，成片建议 GFPGAN 修复；侧脸、暗光、多人会退化；用 Whisper-tiny 提音频特征而非逐音素，唱歌拖腔/颤音表现未知，必须实测。

---

## 三、目录结构

```
mv-lip/
├── input/            用户放剪好的视频（唯一需要你动的地方）
├── output/           成片与中间产物
├── scripts/          本机侧：抽音轨、分离干声、合成、质检
├── kaggle/           GPU 侧：装 MuseTalk、跑推理
├── configs/          MuseTalk 推理配置模板
└── docs/选型对比.md
```

---

## 四、用法

### 第 0 步（一次性）：把视频放进 `input/`

文件名任意，脚本自动取第一个 `.mp4`。要求：**含音乐、25fps、音乐时间轴不要裁剪变速**。

### 第 1 步（本机，CPU 即可）：准备素材

双击 `pipeline.bat` → 选 `1` 准备。它会：
- 用 ffmpeg 抽音轨 → `output/mix.wav`
- 调 demucs 分离 → `output/vocal_dry.wav`（本机 `C:\Python311` 已装 demucs 4.1.0，CPU 跑 18 秒音频约 19 秒）
- 检查/转换视频为 25fps → `output/cut_25fps.mp4`

### 第 2 步（Kaggle，GPU）：对口型

```bash
git clone https://github.com/zhangpengjuGitHub/mv-lip.git
cd mv-lip && bash kaggle/setup_musetalk.sh      # 装环境 + 下权重，约 10-20 分钟
python3 kaggle/run_lipsync.py --video output/cut_25fps.mp4 --audio output/vocal_dry.wav
```

产出 `output/lipsynced.mp4`（无声或带驱动音轨，不用管）。

### 第 3 步（本机）：叠回原混音

双击 `pipeline.bat` → 选 `2` 合成。它把 `lipsynced.mp4` + `output/mix.wav` 合成 `output/final.mp4`，并自动抽 5 帧生成 `output/qc_sheet.jpg` 供目检。

---

## 五、风险清单（还没有实测结论，别跳过）

| 风险 | 说明 | 验证办法 |
|---|---|---|
| **动画角色五官识别** | MuseTalk 的 DWPose / face-parse / S3FD 都是真人训练的。本项目是水墨厚涂角色，厚涂写实风比扁平赛璐璐好识别，但仍是最大不确定项 | 先用纯说话音频跑 5 秒做五官预检，确认能框到脸再上正片 |
| **唱歌 vs 说话** | 主流模型全在说话数据上训练；拖腔、颤音、长音保持未知 | 拿《焚血逃天》副歌 17 秒做 A/B，重点看句首起音、长音「啊」、句尾收音 |
| **静音段嘴还在动** | = 干声没分离干净，伴奏漏进去了 | 间奏纯伴奏段抽帧，嘴应闭合 |
| **口型系统性偏移** | 观众不逐音素比对，但整体错位一眼看穿 | 查句首/长音/句尾三个点；必要时用 ffmpeg `itsoffset` 微调 |

---

## 六、参考

- MuseTalk: https://github.com/TMElyralab/MuseTalk
- LatentSync: https://github.com/bytedance/LatentSync
- video-retalking: https://github.com/OpenTalker/video-retalking
- Wav2Lip: https://github.com/Rudrabha/Wav2Lip
- 干声分离 demucs: https://github.com/facebookresearch/demucs
