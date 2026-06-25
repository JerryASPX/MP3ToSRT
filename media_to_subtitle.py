#!/usr/bin/env python
"""Convert audio/video files to subtitle files using faster-whisper.

Outputs:
- .srt for common subtitle use and YouTube upload
- .vtt WebVTT, also accepted by YouTube
- optional .txt transcript
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def format_srt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def format_vtt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Avoid malformed SRT/VTT arrow tokens inside subtitle text.
    return text.replace("-->", "→")


def convert_chinese_text(text: str, mode: str) -> str:
    """Convert Chinese subtitle text with OpenCC.

    mode choices:
    - none: leave model output unchanged
    - tw: Taiwan Traditional Chinese, including common Taiwan phrase variants
    - hk: Hong Kong Traditional Chinese
    - t: generic Traditional Chinese
    """
    if mode == "none":
        return text
    config_by_mode = {
        "tw": "s2twp",
        "hk": "s2hk",
        "t": "s2t",
    }
    try:
        from opencc import OpenCC
    except ImportError:
        die("Missing dependency opencc. Run: python -m pip install opencc-python-reimplemented")
    converter = OpenCC(config_by_mode[mode])
    return converter.convert(text)


BUILTIN_CORRECTION_RULES = [
    {"wrong": "換姿術", "right": "換姿勢", "hints": ["出門", "活動", "手", "酸", "姿"]},
    {"wrong": "資術", "right": "姿勢", "hints": ["換", "活動", "手", "酸"]},
    {"wrong": "姿術", "right": "姿勢", "hints": ["換", "活動", "手", "酸"]},
    {"wrong": "字幕黨", "right": "字幕檔", "hints": ["上傳", "YouTube", "SRT", "VTT", "檔案"]},
    {"wrong": "優兔", "right": "YouTube", "hints": ["字幕", "上傳", "影片"]},
]


def load_correction_rules(path: Path | None) -> list[dict]:
    """Load phrase correction rules.

    Rules are conservative: each rule needs a wrong/right pair and optional hints.
    If hints are provided, at least one hint must appear in the full transcript before
    the replacement is applied. This gives a light-weight context check and avoids
    replacing homophones blindly in unrelated sentences.
    """
    rules = list(BUILTIN_CORRECTION_RULES)
    if path and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            custom = data.get("rules", data if isinstance(data, list) else [])
            if isinstance(custom, list):
                for item in custom:
                    if isinstance(item, dict) and item.get("wrong") and item.get("right"):
                        rules.append(
                            {
                                "wrong": str(item["wrong"]),
                                "right": str(item["right"]),
                                "hints": [str(h) for h in item.get("hints", [])],
                            }
                        )
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to load corrections from {path}: {exc}", file=sys.stderr)
    # Longer wrong phrases first so specific phrases win before shorter fragments.
    return sorted(rules, key=lambda r: len(r["wrong"]), reverse=True)


def apply_context_corrections(segments: list[dict], rules: list[dict]) -> tuple[list[dict], list[str]]:
    full_text = "\n".join(clean_text(seg.get("text", "")) for seg in segments)
    changes: list[str] = []
    corrected: list[dict] = []
    for seg in segments:
        text = clean_text(seg.get("text", ""))
        for rule in rules:
            wrong = rule["wrong"]
            right = rule["right"]
            hints = rule.get("hints") or []
            if wrong in text and (not hints or any(hint in full_text for hint in hints)):
                text = text.replace(wrong, right)
                change = f"{wrong} → {right}"
                if change not in changes:
                    changes.append(change)
        corrected.append({**seg, "text": text})
    return corrected, changes


def write_srt(path: Path, segments: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="\n") as f:
        for i, seg in enumerate(segments, start=1):
            text = clean_text(seg["text"])
            if not text:
                continue
            f.write(f"{i}\n")
            f.write(f"{format_srt_time(seg['start'])} --> {format_srt_time(seg['end'])}\n")
            f.write(f"{text}\n\n")


def write_vtt(path: Path, segments: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("WEBVTT\n\n")
        for seg in segments:
            text = clean_text(seg["text"])
            if not text:
                continue
            f.write(f"{format_vtt_time(seg['start'])} --> {format_vtt_time(seg['end'])}\n")
            f.write(f"{html.escape(text)}\n\n")


def write_txt(path: Path, segments: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for seg in segments:
            text = clean_text(seg["text"])
            if text:
                f.write(text + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert an audio/video file into SRT and/or YouTube-ready subtitle files."
    )
    parser.add_argument("input", help="Input audio/video file, e.g. mp4, mov, mp3, wav, m4a")
    parser.add_argument("-o", "--output-dir", default=None, help="Output folder. Default: same folder as input")
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model size/name: tiny, base, small, medium, large-v3, etc. Default: small",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code, e.g. zh, en, ja. Default: auto-detect",
    )
    parser.add_argument(
        "--task",
        choices=["transcribe", "translate"],
        default="transcribe",
        help="transcribe keeps original language; translate outputs English. Default: transcribe",
    )
    parser.add_argument(
        "--format",
        choices=["srt", "vtt", "txt", "all"],
        default="all",
        help="Output format. YouTube accepts .srt and .vtt. Default: all",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda", "auto"],
        help="Use cpu, cuda, or auto. Default: cpu",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="faster-whisper compute type. CPU default int8; CUDA can use float16.",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam size. Higher can improve accuracy but is slower. Default: 5",
    )
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        help="Enable voice activity detection to skip silence/noise.",
    )
    parser.add_argument(
        "--chinese",
        choices=["none", "tw", "hk", "t"],
        default="tw",
        help="Chinese conversion for subtitle output: tw=Taiwan Traditional (default), hk=Hong Kong Traditional, t=generic Traditional, none=no conversion.",
    )
    parser.add_argument(
        "--auto-correct",
        dest="auto_correct",
        action="store_true",
        default=True,
        help="Apply context-aware correction rules after transcription. Enabled by default.",
    )
    parser.add_argument(
        "--no-auto-correct",
        dest="auto_correct",
        action="store_false",
        help="Disable context-aware correction rules.",
    )
    parser.add_argument(
        "--corrections",
        default=str(Path(__file__).resolve().parent / "corrections.json"),
        help="JSON correction rules file. Default: corrections.json next to this script.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        die(f"Input file not found: {input_path}")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die(
            "Missing dependency faster-whisper. Run: python -m pip install faster-whisper"
        )

    print(f"Loading Whisper model: {args.model} ({args.device}, {args.compute_type})")
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    print(f"Transcribing: {input_path}")
    segments_iter, info = model.transcribe(
        str(input_path),
        language=args.language,
        task=args.task,
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
    )
    segments = [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": convert_chinese_text(clean_text(s.text), args.chinese),
        }
        for s in segments_iter
        if clean_text(s.text)
    ]

    if not segments:
        die("No speech segments were detected. Try a clearer file or disable/enable --vad-filter.")

    if args.auto_correct:
        rules = load_correction_rules(Path(args.corrections).expanduser())
        segments, correction_changes = apply_context_corrections(segments, rules)
    else:
        correction_changes = []

    detected = getattr(info, "language", None) or "unknown"
    prob = getattr(info, "language_probability", None)
    if prob is not None:
        print(f"Detected language: {detected} ({prob:.2%})")
    else:
        print(f"Detected language: {detected}")
    if args.auto_correct:
        if correction_changes:
            print("Context corrections applied:")
            for change in correction_changes:
                print(f"- {change}")
        else:
            print("Context corrections applied: none")

    outputs: list[Path] = []
    formats = ["srt", "vtt", "txt"] if args.format == "all" else [args.format]
    if "srt" in formats:
        path = out_dir / f"{stem}.srt"
        write_srt(path, segments)
        outputs.append(path)
    if "vtt" in formats:
        path = out_dir / f"{stem}.vtt"
        write_vtt(path, segments)
        outputs.append(path)
    if "txt" in formats:
        path = out_dir / f"{stem}.txt"
        write_txt(path, segments)
        outputs.append(path)

    print("Generated:")
    for path in outputs:
        print(f"- {path}")
    print("\nYouTube Studio > 字幕 > 新增語言 > 新增 > 上傳檔案，可直接上傳 .srt 或 .vtt。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
