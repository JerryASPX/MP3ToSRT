# 影音轉字幕工具

## 單張網頁使用者介面

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

## GitHub Pages 注意事項

GitHub Pages 網址：

```text
https://jerryaspx.github.io/MP3ToSRT/
```

這個網址只能展示單頁 UI 與原始碼，不能直接轉字幕。原因是 GitHub Pages 只能執行靜態 HTML/CSS/JavaScript，不能執行本工具需要的 Python、faster-whisper、ffmpeg 後端。

要實際轉字幕，請在本機啟動：

```bash
cd /c/Users/Jerry/subtitle_tool
./.venv/Scripts/python server.py
```

然後開啟：

```text
http://127.0.0.1:8766/
```

若要讓網路上的使用者也能直接轉字幕，需要另外部署 Python 後端到 Render、Railway、Fly.io、VPS 或 Hugging Face Spaces 等支援長時間運算與檔案上傳的平台。

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
