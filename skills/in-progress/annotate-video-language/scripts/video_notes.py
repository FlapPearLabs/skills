#!/usr/bin/env python3
"""Prepare evidence and render agent-authored video annotations; no semantic AI claims."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = ImageDraw = ImageFont = ImageOps = None

ROOT = Path(__file__).resolve().parents[1]
CONFIDENCE = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}


def run(args, timeout=900):
    result = subprocess.run([str(x) for x in args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"{Path(str(args[0])).name} 执行失败：" + result.stderr.decode("utf-8", "replace")[-3000:])
    return result


def need_tools():
    if Image is None:
        raise ValueError("缺少 Pillow，请在当前 Python 环境安装后重试")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            raise ValueError(f"缺少 {name}，请在宿主允许范围内安装")


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} 必须是有限数字")
    return float(value)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def probe(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]).stdout)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if not v:
        raise ValueError("输入没有视频轨道")
    duration = float(v.get("duration") or data.get("format", {}).get("duration") or 0)
    if duration <= 0 or not math.isfinite(duration):
        raise ValueError("无法取得有效的视频时长")
    try:
        fps = float(Fraction(v.get("avg_frame_rate", "0/1")))
    except (ValueError, ZeroDivisionError):
        fps = 0
    if fps <= 0:
        fps = 25.0
    try:
        sar = float(Fraction(v.get("sample_aspect_ratio", "1:1").replace(":", "/")))
    except (ValueError, ZeroDivisionError):
        sar = 1.0
    if not math.isfinite(sar) or sar <= 0:
        sar = 1.0
    rotation = next((float(x["rotation"]) for x in v.get("side_data_list", []) if "rotation" in x), 0)
    w, h = round(v["width"] * sar), v["height"]
    if round(rotation) % 180:
        w, h = h, w
    return {"duration": duration, "fps": fps, "width": w, "height": h,
            "video_start": float(v.get("start_time", 0)), "has_audio": any(s.get("codec_type") == "audio" for s in data["streams"])}


def new_directory(path):
    path = Path(path).resolve()
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"输出目录已有内容，请使用新目录：{path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fonts(explicit=None):
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise ValueError(f"字体不存在：{p}")
        return [p]
    candidates = [ROOT / "assets/VideoNotesSC-Regular.ttf",
                  Path("/System/Library/Fonts/PingFang.ttc"), Path("/System/Library/Fonts/STHeiti Light.ttc"),
                  Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
                  Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    return [p for p in candidates if p.is_file()]


def choose_font(text, explicit=None, size=26):
    for path in fonts(explicit):
        f = ImageFont.truetype(str(path), size)
        missing = bytes(f.getmask("\U0010ffff"))
        if not any(bytes(f.getmask(c)) == missing for c in set(text) if not c.isspace()):
            return path
    raise ValueError("没有能完整显示标注文字的字体；请用 --font 指定含所需字形的中文字体")


def doctor(args):
    data = {"python": sys.version.split()[0], "pillow": Image is not None,
            "commands": {x: shutil.which(x) for x in ("ffmpeg", "ffprobe")},
            "fonts": [str(x) for x in fonts(args.font)], "platform": sys.platform,
            "graphics_session": sys.platform in ("darwin", "win32") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            "semantic_analysis": "需要执行模型实际查看画面；脚本不做镜头语义识别"}
    data["ready"] = Image is not None and all(data["commands"].values()) and bool(data["fonts"])
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data["ready"] else 2


def cut_candidates(source, threshold, info):
    filt = f"setpts=PTS-STARTPTS,select='gt(scene,{threshold})',showinfo"
    result = run(["ffmpeg", "-hide_banner", "-i", source, "-vf", filt, "-an", "-f", "null", "-"])
    times = sorted(float(t) for t in re.findall(r"pts_time:\s*([0-9.+eE-]+)", result.stderr.decode("utf-8", "replace")))
    merged = []
    for t in times:
        if 1 / info["fps"] < t < info["duration"] - 1 / info["fps"] and (not merged or t - merged[-1] > 0.12):
            merged.append(t)
    return merged


def grab(source, time, target):
    run(["ffmpeg", "-v", "error", "-ss", f"{time:.6f}", "-i", source, "-frames:v", "1",
         "-vf", "scale='min(960,iw)':-2", "-q:v", "3", "-update", "1", "-y", target])
    if not target.is_file() or not target.stat().st_size:
        raise ValueError(f"无法取出 {time:.3f} 秒画面")


def make_sheets(frames, out, explicit=None):
    folder = out / "contact-sheets"
    folder.mkdir(exist_ok=True)
    paths = fonts(explicit)
    font = ImageFont.truetype(str(paths[0]), 19) if paths else ImageFont.load_default()
    sheets = []
    for page in range(0, len(frames), 20):
        batch = frames[page:page + 20]
        sheet = Image.new("RGB", (1200, math.ceil(len(batch) / 4) * 270), "#18212c")
        draw = ImageDraw.Draw(sheet)
        for i, frame in enumerate(batch):
            im = Image.open(out / frame["file"]).convert("RGB")
            im.thumbnail((290, 235))
            x, y = (i % 4) * 300, (i // 4) * 270
            sheet.paste(im, (x + (300 - im.width) // 2, y))
            draw.text((x + 8, y + 241), f"{Path(frame['file']).stem}   {frame['time']:.3f}s", font=font, fill="white")
        dest = folder / f"sheet-{page // 20 + 1:03}.jpg"
        sheet.save(dest, quality=90)
        sheets.append(str(dest.relative_to(out)))
    return sheets


def prepare(args):
    need_tools()
    source = Path(args.input).expanduser().resolve(strict=True)
    info = probe(source)
    if args.step <= 0 or not math.isfinite(args.step) or not 0 < args.threshold < 1:
        raise ValueError("step 必须大于零，threshold 必须位于零和一之间")
    cuts = cut_candidates(source, args.threshold, info)
    times = {0.0}
    for i in range(math.ceil(info["duration"] / args.step)):
        times.add(i * args.step)
    edges = [0.0] + cuts + [info["duration"]]
    for a, b in zip(edges, edges[1:]):
        for fraction in (0.1, 0.5, 0.9):
            times.add(a + (b - a) * fraction)
    for c in cuts:
        for offset in (-0.28, -0.08, 0.08, 0.28):
            times.add(c + offset)
    end = max(0, info["duration"] - 0.5 / info["fps"])
    times = sorted({round(min(max(t, 0), end), 6) for t in times})
    return sample(source, info, times, cuts, args)


def sample(source, info, times, cuts, args):
    if len(times) > args.max_frames:
        raise ValueError(f"需要 {len(times)} 张证据帧，超过 max-frames={args.max_frames}；增加限额或先分段，不能静默跳过")
    out = new_directory(args.out)
    (out / "frames").mkdir()
    records = []
    for i, t in enumerate(times):
        relative = f"frames/f{i + 1:04}.jpg"
        grab(source, t, out / relative)
        records.append({"time": t, "file": relative})
    source_data = {"path": str(source), "sha256": digest(source), **info}
    manifest = {"source": source_data, "candidate_cuts": cuts, "frames": records,
                "contact_sheets": make_sheets(records, out, args.font),
                "warning": "候选边界未经语义确认；时间是请求取样时间，可能相差一帧"}
    write_json(out / "manifest.json", manifest)
    write_json(out / "analysis.template.json", {"schema_version": 1, "source": source_data,
               "review": {"visual": "pending", "audio": "unavailable" if info["has_audio"] else "no-audio"}, "shots": [], "joins": []})
    print(json.dumps({"output": str(out), "frames": len(records), "candidate_cuts": cuts, "semantic_review": "pending"}, ensure_ascii=False))
    return 0


def window(args):
    need_tools()
    source = Path(args.input).expanduser().resolve(strict=True)
    info = probe(source)
    if not all(math.isfinite(x) for x in (args.start, args.end, args.fps)) or not 0 <= args.start < args.end <= info["duration"] or args.fps <= 0:
        raise ValueError("窗口起止或 fps 无效")
    count = math.ceil((args.end - args.start) * args.fps)
    times = [round(min(args.start + i / args.fps, info["duration"] - 0.5 / info["fps"]), 6) for i in range(count)]
    return sample(source, info, times, [], args)


def nonempty(obj, key):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        raise ValueError(f"缺少有效文字字段：{key}")


def evidence(items, lo, hi, base, minimum):
    if not isinstance(items, list) or len(items) < minimum:
        raise ValueError(f"需要至少 {minimum} 个实际证据画面")
    times = []
    for item in items:
        t = number(item.get("time"), "证据时间")
        if not lo <= t <= hi:
            raise ValueError("证据时间超出对应区间")
        nonempty(item, "file")
        path = (base / item["file"]).resolve()
        if not path.is_file():
            raise ValueError(f"证据图片不存在：{path}")
        with Image.open(path) as image:
            image.verify()
        times.append(t)
    if len(set(times)) < minimum:
        raise ValueError("重复时间不能充当多个连续画面证据")
    return times


def validate(source, analysis_path):
    need_tools()
    source = Path(source).expanduser().resolve(strict=True)
    analysis_path = Path(analysis_path).expanduser().resolve(strict=True)
    a = json.loads(analysis_path.read_text(encoding="utf-8"))
    if a.get("schema_version") != 1:
        raise ValueError("不支持的标注格式版本")
    info = probe(source)
    tolerance = max(1 / info["fps"], 0.002)
    if a.get("source", {}).get("sha256") != digest(source):
        raise ValueError("源视频指纹不匹配，禁止套用其他视频的标注")
    if abs(number(a["source"].get("duration"), "源时长") - info["duration"]) > tolerance:
        raise ValueError("源视频时长不匹配")
    review = a.get("review", {})
    if review.get("visual") != "complete":
        raise ValueError("视觉检查尚未完成，拒绝渲染待核对模板")
    if review.get("audio") not in ("listened", "unavailable", "no-audio"):
        raise ValueError("音频检查状态无效")
    if info["has_audio"] == (review["audio"] == "no-audio"):
        raise ValueError("音频状态与实际音轨不符")
    shots, joins = a.get("shots"), a.get("joins")
    if not isinstance(shots, list) or not shots or not isinstance(joins, list):
        raise ValueError("需要完整镜头表和接点数组")
    ids, previous = set(), 0.0
    for s in shots:
        nonempty(s, "id")
        if s["id"] in ids:
            raise ValueError("镜头 ID 重复")
        ids.add(s["id"])
        start, end = number(s.get("start"), "镜头起点"), number(s.get("end"), "镜头终点")
        if not 0 <= start < end <= info["duration"] + 0.0001 or abs(start - previous) > 0.0001:
            raise ValueError("镜头表存在越界、空隙、重叠或顺序错误")
        for key in ("observed", "subject_motion", "camera_motion", "depth", "generation_prompt", "edit_instruction"):
            nonempty(s, key)
        if not isinstance(s.get("terms"), list) or not s["terms"] or not all(isinstance(x, str) and x.strip() for x in s["terms"]):
            raise ValueError("术语必须是非空文字数组")
        if s.get("confidence") not in CONFIDENCE:
            raise ValueError("镜头置信度无效")
        evidence(s.get("evidence"), start, min(end, info["duration"]), analysis_path.parent, 1 if end - start <= tolerance * 1.1 else 2)
        previous = end
    if abs(previous - info["duration"]) > tolerance:
        raise ValueError("镜头表没有覆盖视频结尾")
    if len(joins) != len(shots) - 1:
        raise ValueError("必须覆盖每对相邻镜头的接点，包括硬切")
    join_ids = set()
    for j, left, right in zip(joins, shots, shots[1:]):
        nonempty(j, "id")
        if j["id"] in join_ids:
            raise ValueError("接点 ID 重复")
        join_ids.add(j["id"])
        if (j.get("from_shot"), j.get("to_shot")) != (left["id"], right["id"]):
            raise ValueError("接点与相邻镜头不对应")
        start, end, cut = (number(j.get(k), k) for k in ("start", "end", "cut_time"))
        if not 0 <= start <= cut <= end <= info["duration"] or end <= start or abs(cut - right["start"]) > tolerance:
            raise ValueError("接点区间或切点无效")
        for key in ("type", "observed", "continuity", "generation_constraints", "edit_instruction", "audio_observed"):
            nonempty(j, key)
        if j.get("confidence") not in CONFIDENCE:
            raise ValueError("接点置信度无效")
        ts = evidence(j.get("evidence"), start, end, analysis_path.parent, 2)
        if not any(t < cut for t in ts) or not any(t >= cut for t in ts):
            raise ValueError("接点证据必须包含切点两侧画面")
    return a, info


def rows_for(shot, join):
    if join:
        return [(f"{join['id']}  接点 {join['cut_time']:.2f}秒  置信：{CONFIDENCE[join['confidence']]}", "title"),
                ("方式：" + join["type"], "accent"), ("观察：" + join["observed"], "text"),
                ("剪辑：" + join["edit_instruction"], "text")]
    return [(f"{shot['id']}  {shot['start']:.2f} 至 {shot['end']:.2f}秒  置信：{CONFIDENCE[shot['confidence']]}", "title"),
            ("术语：" + "、".join(shot["terms"]), "accent"), ("观察：" + shot["observed"], "text"),
            ("生成：" + shot["generation_prompt"], "text")]


def split_lines(draw, text, font, width):
    lines, current = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
        elif current and draw.textlength(current + ch, font=font) > width:
            lines.append(current)
            current = ch
        else:
            current += ch
    return lines + ([current] if current else [])


def card(rows, width, height, font_path):
    im = Image.new("RGB", (width, height), "#111b27")
    draw = ImageDraw.Draw(im)
    scale = width / 960
    pad, y = round(28 * scale), round(20 * scale)
    for text, style in rows:
        size = max(14, round((29 if style == "title" else 26) * scale))
        font = ImageFont.truetype(str(font_path), size)
        line_height = round(size * 1.55)
        lines = split_lines(draw, text, font, width - pad * 2)
        limit = 1 if style in ("title", "accent") else 3
        truncated = len(lines) > limit
        lines = lines[:limit]
        if truncated:
            suffix = "…续见说明文档"
            while lines[-1] and draw.textlength(lines[-1] + suffix, font=font) > width - pad * 2:
                lines[-1] = lines[-1][:-1]
            lines[-1] += suffix
        for line in lines:
            if y + line_height > height - 8:
                raise ValueError("标注卡片空间不足，请增大 --panel-height")
            draw.text((pad, y), line, font=font, fill={"title": "#ffffff", "accent": "#6de2c4", "text": "#dee7f1"}[style])
            y += line_height
        y += round(8 * scale)
    return im


def report(a, source, destination):
    lines = ["# 镜头与剪辑说明", "", f"视频：{source.name}", f"视觉检查：{a['review']['visual']}；音频检查：{a['review']['audio']}",
             "", "本文件中的观察来自执行模型；生成与剪辑指令是复刻建议，不代表原作者真实制作过程。", ""]
    for s in a["shots"]:
        lines += [f"## {s['id']}｜{s['start']:.3f}–{s['end']:.3f} 秒", "", f"术语：{'、'.join(s['terms'])}；置信度：{CONFIDENCE[s['confidence']]}", ""]
        for key, label in (("observed", "实际观察"), ("subject_motion", "主体动作"), ("camera_motion", "镜头运动"), ("depth", "景深效果"), ("generation_prompt", "给 AI 的生成描述"), ("edit_instruction", "真实素材剪辑建议")):
            lines += [f"{label}：{s[key]}", ""]
        lines += ["证据：" + "；".join(f"{e['time']:.3f}秒（{e['file']}）" for e in s["evidence"]), ""]
    for j in a["joins"]:
        lines += [f"## {j['id']}｜{j['from_shot']} → {j['to_shot']}｜切点 {j['cut_time']:.3f} 秒", "", f"检查区间：{j['start']:.3f}–{j['end']:.3f}秒；置信度：{CONFIDENCE[j['confidence']]}", ""]
        for key, label in (("type", "方式"), ("observed", "实际观察"), ("continuity", "如何衔接"), ("generation_constraints", "生成素材的起止条件"), ("edit_instruction", "剪辑步骤"), ("audio_observed", "声音检查")):
            lines += [f"{label}：{j[key]}", ""]
        lines += ["证据：" + "；".join(f"{e['time']:.3f}秒（{e['file']}）" for e in j["evidence"]), ""]
    destination.write_text("\n".join(lines), encoding="utf-8")


def open_player(path, disabled=False):
    if disabled:
        return {"status": "unavailable", "reason": "已禁用本机打开；通过当前宿主交付文件"}
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            run(["open", path], timeout=20)
        elif (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and shutil.which("xdg-open"):
            run(["xdg-open", path], timeout=20)
        else:
            return {"status": "unavailable", "reason": "当前进程没有可用的本机图形会话"}
        return {"status": "requested", "reason": "操作系统已接受打开请求；播放器窗口与播放状态尚未确认"}
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"status": "failed", "reason": str(e)[:500]}


def render(args):
    source = Path(args.input).expanduser().resolve(strict=True)
    a, info = validate(source, args.analysis)
    if args.width < 480 or args.panel_height < 260:
        raise ValueError("width 至少 480，panel-height 至少 260")
    width = args.width // 2 * 2
    video_height = round(width * info["height"] / info["width"] / 2) * 2
    panel_height = round(args.panel_height * width / 960 / 2) * 2
    if panel_height < 200:
        panel_height = 200
    breaks = {0.0, info["duration"]}
    ranges = []
    for s in a["shots"]:
        breaks.update((s["start"], min(info["duration"], s["end"])))
    for j in a["joins"]:
        start = max(0, min(j["start"], j["cut_time"] - 0.55))
        end = min(info["duration"], max(j["end"], j["cut_time"] + 0.85))
        ranges.append((start, end, j))
        breaks.update((start, end))
    points = sorted(breaks)
    segments = []
    for left, right in zip(points, points[1:]):
        middle = (left + right) / 2
        shot = next((s for s in a["shots"] if s["start"] <= middle < s["end"]), a["shots"][-1])
        candidates = [j for lo, hi, j in ranges if lo <= middle < hi]
        join = min(candidates, key=lambda j: abs(j["cut_time"] - middle)) if candidates else None
        segments.append((left, right, rows_for(shot, join)))
    text = "".join(t for _, _, rows in segments for t, _ in rows) + "…续见说明文档"
    font_path = choose_font(text, args.font)
    out = new_directory(args.out)
    cards = out / "cards"
    cards.mkdir()
    concat_lines = ["ffconcat version 1.0"]
    for i, (left, right, rows) in enumerate(segments):
        relative = f"cards/card-{i:04}.png"
        card(rows, width, panel_height, font_path).save(out / relative)
        concat_lines += [f"file '{relative}'", f"duration {right - left:.9f}"]
    concat_lines += [f"file 'cards/card-{len(segments) - 1:04}.png'"]
    concat = out / "cards.ffconcat"
    concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    output = out / "镜头与剪辑标注.mp4"
    filt = f"[0:v:0]setpts=PTS-STARTPTS,scale={width}:{video_height},setsar=1,pad={width}:{video_height + panel_height}:0:0:color=0x111b27[base];[1:v:0]setpts=PTS-STARTPTS[notes];[base][notes]overlay=0:{video_height}:eof_action=repeat:shortest=0[v]"
    command = ["ffmpeg", "-v", "error", "-copyts", "-i", source, "-f", "concat", "-safe", "1", "-i", concat,
               "-filter_complex", filt, "-map", "[v]", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if info["has_audio"]:
        command += ["-af", f"atrim=start={info['video_start']:.9f},asetpts=PTS-{info['video_start']:.9f}/TB", "-c:a", "aac"]
    command += ["-t", f"{info['duration']:.9f}", "-movflags", "+faststart", "-y", output]
    run(command, timeout=3600)
    actual = probe(output)
    if abs(actual["duration"] - info["duration"]) > max(0.15, 2 / info["fps"]) or actual["has_audio"] != info["has_audio"]:
        raise ValueError("导出时长或音轨检查失败")
    run(["ffmpeg", "-v", "error", "-i", output, "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"], timeout=3600)
    report(a, source, out / "镜头与剪辑说明.md")
    opening = open_player(output, args.no_local_open) if args.open else {"status": "unavailable", "reason": "本次未指定 --open"}
    write_json(out / "open_result.json", opening)
    result = {"video": str(output), "report": str(out / "镜头与剪辑说明.md"), "shots": len(a["shots"]), "joins": len(a["joins"]),
              "duration": actual["duration"], "audio": actual["has_audio"], "font": str(font_path), "open": opening}
    write_json(out / "render_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="为视频取样，校验模型填写的分析，并渲染中文标注视频")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor")
    p.add_argument("--font")
    p.set_defaults(func=doctor)
    for name, fn in (("prepare", prepare), ("window", window)):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--font")
        p.add_argument("--max-frames", type=int, default=500)
        if name == "prepare":
            p.add_argument("--step", type=float, default=1.0)
            p.add_argument("--threshold", type=float, default=0.32)
        else:
            p.add_argument("--start", type=float, required=True)
            p.add_argument("--end", type=float, required=True)
            p.add_argument("--fps", type=float, default=12)
        p.set_defaults(func=fn)
    p = sub.add_parser("validate")
    p.add_argument("--input", required=True)
    p.add_argument("--analysis", required=True)
    p.set_defaults(func=lambda a: (validate(a.input, a.analysis), print("标注校验通过"), 0)[-1])
    p = sub.add_parser("render")
    p.add_argument("--input", required=True)
    p.add_argument("--analysis", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--font")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--panel-height", type=int, default=460)
    p.add_argument("--open", action="store_true")
    p.add_argument("--no-local-open", action="store_true")
    p.set_defaults(func=render)
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
