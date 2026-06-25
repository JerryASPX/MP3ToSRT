# 影音轉字幕工具

## GitHub Pages 瀏覽器版

可直接開啟：

```text
https://jerryaspx.github.io/MP3ToSRT/
```

GitHub Pages 版會在使用者瀏覽器內執行 Whisper WebAssembly 模型，不需要 Python 後端；影片/音檔留在本機瀏覽器中處理，不會上傳到伺服器。

瀏覽器版功能：

- 直接選擇影片 / 音檔
- 產生 YouTube 可用 `.srt` / `.vtt`
- 產生 `.txt` 逐字稿
- 完成後在網頁上提供 `.srt` / `.vtt` / `.txt` 下載連結
- 台灣繁體中文轉換
- 分析上下文並修正可能錯字

限制：瀏覽器版適合短音檔或短影片；第一次使用會下載模型，檔案越長越慢。為避免網頁看起來卡住，GitHub Pages 版預設使用最快的 tiny 模型，並會在執行記錄中顯示「載入模型、解碼音訊、開始辨識」等階段提示。若影片超過數分鐘或超過 50MB，建議改用下面的本機 Python 版。

## 本機 Python 版使用者介面

啟動本機網頁：

```bash
cd /c/Users/Jerry/subtitle_tool
./.venv/Scripts/python server.py
```

然後用瀏覽器開啟：

```text
http://127.0.0.1:8766/
```

網頁可以：

- 貼上本機影片 / 音檔路徑後產生字幕
- 或直接選擇檔案上傳到工具資料夾再轉字幕
- 輸出台灣繁體中文
- 產生 YouTube 可用的 `.srt` / `.vtt`
- 顯示轉檔狀態、字幕預覽、下載連結
- 分析上下文並依詞庫修正可能錯字，例如「換姿術」→「換姿勢」

## 架構說明

- GitHub Pages：純前端瀏覽器版，使用 transformers.js / Whisper WebAssembly；不需 Python 後端，但速度與模型大小受瀏覽器限制。
- 本機 Python 版：使用 `server.py` + `faster-whisper`，較適合長影片與較高準確度需求。

## 命令列版本

這個工具可以把影片檔或音檔轉成字幕檔：

- `.srt`：一般字幕檔，YouTube 可直接上傳
- `.vtt`：WebVTT，YouTube 也可直接上傳
- `.txt`：純文字逐字稿

## 第一次安裝

在 `C:\Users\Jerry\subtitle_tool` 執行：

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install --upgrade pip
./.venv/Scripts/python -m pip install faster-whisper
```

## 使用方式

```bash
cd /c/Users/Jerry/subtitle_tool
./.venv/Scripts/python media_to_subtitle.py "C:/路徑/你的影片.mp4" --language zh --model small --format all --chinese tw
```

輸出會放在原始檔同一個資料夾：

- `你的影片.srt`
- `你的影片.vtt`
- `你的影片.txt`

指定輸出資料夾：

```bash
./.venv/Scripts/python media_to_subtitle.py "C:/路徑/你的音檔.mp3" -o "C:/Users/Jerry/Desktop/subtitles" --language zh
```

## YouTube 上傳

YouTube Studio → 字幕 → 新增語言 → 新增 → 上傳檔案：

- 若選 `.srt`：選「含有時間碼」
- 若選 `.vtt`：也可直接上傳

## 常用參數

- `--language zh`：中文；英文用 `en`，日文用 `ja`，不填則自動偵測
- `--chinese tw`：輸出台灣繁體中文，這是預設值；若要保留原始辨識結果可用 `--chinese none`
- `--auto-correct` / `--no-auto-correct`：預設會分析上下文並套用 `corrections.json` 錯字修正詞庫
- `--model tiny|base|small|medium|large-v3`：越大越準但越慢；預設 `small`
- `--format srt|vtt|txt|all`：預設 `all`
- `--vad-filter`：嘗試跳過靜音或噪音
- `--device cuda --compute-type float16`：若有 NVIDIA GPU 可用這組加速
