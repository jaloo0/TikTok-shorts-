#!/usr/bin/env python3
"""Create a vertical short using yt-dlp, optional AI clip selection, and FFmpeg."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import Any
import requests
import yt_dlp

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def run(command: list[str], capture: bool = False):
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)

def require_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe): raise RuntimeError(f"{exe} not found; install FFmpeg.")

def download_video(url: str, out_dir: Path) -> Path:
    opts = {"outtmpl": str(out_dir / "source.%(ext)s"), "format": "bv*[height<=1080]+ba/b[height<=1080]/best", "merge_output_format": "mp4", "noplaylist": True, "retries": 3, "fragment_retries": 3}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        candidate = Path(ydl.prepare_filename(info))
    if candidate.exists(): return candidate
    if candidate.with_suffix('.mp4').exists(): return candidate.with_suffix('.mp4')
    matches = [p for p in out_dir.glob('source.*') if p.suffix.lower() not in {'.part', '.ytdl'}]
    if not matches: raise FileNotFoundError('yt-dlp finished but source file was not found')
    return matches[0]

def get_duration(path: Path) -> float:
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)], True).stdout.strip())

def transcribe(path: Path) -> list[dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv('WHISPER_MODEL','base'), device='cpu', compute_type='int8')
        segments, _ = model.transcribe(str(path), vad_filter=True)
        return [{'start':float(s.start),'end':float(s.end),'text':s.text.strip()} for s in segments if s.text.strip()]
    except ImportError:
        try: import whisper
        except ImportError:
            print('Whisper unavailable; using a centered fallback clip.', flush=True); return []
        result = whisper.load_model(os.getenv('WHISPER_MODEL','base')).transcribe(str(path), fp16=False)
        return [{'start':float(s['start']),'end':float(s['end']),'text':s['text'].strip()} for s in result.get('segments',[]) if s.get('text','').strip()]

def validate_clip(data: dict, duration: float) -> tuple[float,float]:
    start, end = float(data['start']), float(data['end'])
    if start < 0 or end <= start or start >= duration: raise ValueError('AI returned invalid timestamps')
    start, end = max(0.0,start), min(duration,end)
    if end-start > 60: end = start+60
    if end-start < 8: end = min(duration,start+20)
    return start,end

def choose_gemini(segments, duration):
    key, model = os.getenv('GEMINI_API_KEY','').strip(), os.getenv('GEMINI_MODEL','').strip()
    if os.getenv('USE_GEMINI','false').lower() != 'true' or not key or not model or not segments: return None
    transcript = '\n'.join(f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in segments)
    prompt = f'Select one engaging self-contained 15-60 second clip. Return only JSON with numeric start and end fields. Source duration {duration:.2f}s. Transcript:\n{transcript}'
    r = requests.post(GEMINI_URL.format(model=model), params={'key':key}, json={'contents':[{'parts':[{'text':prompt}]}], 'generationConfig':{'temperature':0.2,'responseMimeType':'application/json'}}, timeout=90)
    r.raise_for_status(); return validate_clip(json.loads(r.json()['candidates'][0]['content']['parts'][0]['text']), duration)

def choose_openrouter(segments, duration):
    key, model = os.getenv('OPENROUTER_API_KEY','').strip(), os.getenv('OPENROUTER_MODEL','').strip()
    if not key or not model or model.lower() == 'none' or not segments: return None
    transcript = '\n'.join(f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in segments)
    prompt = f'Choose the funniest, most surprising, or most engaging self-contained 15-60 second excerpt. Return only JSON: {{"start": number, "end": number}}. Source duration {duration:.2f}s. Transcript:\n{transcript}'
    r = requests.post(OPENROUTER_URL, headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}, json={'model':model,'messages':[{'role':'system','content':'Select short clips and return only valid JSON.'},{'role':'user','content':prompt}],'temperature':0.2}, timeout=90)
    r.raise_for_status(); content = r.json()['choices'][0]['message']['content'].strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    return validate_clip(json.loads(content), duration)

def select_clip(segments, duration):
    if os.getenv('USE_GEMINI','false').lower() == 'true':
        try:
            selected = choose_gemini(segments,duration)
            if selected: print('Clip selection: Gemini'); return selected
        except Exception as exc: print(f'Gemini failed; falling back: {exc}', flush=True)
    try:
        selected = choose_openrouter(segments,duration)
        if selected: print('Clip selection: OpenRouter'); return selected
    except Exception as exc: print(f'OpenRouter failed; using fallback: {exc}', flush=True)
    if segments:
        length = min(30.0,duration); best = (0.0,length,-1.0)
        for seg in segments:
            start = max(0.0,min(float(seg['start']),max(0.0,duration-length))); end = min(duration,start+length)
            score = sum(max(0.0,min(float(s['end']),end)-max(float(s['start']),start)) for s in segments)
            if score > best[2]: best = (start,end,score)
        return best[0],best[1]
    start = max(0.0,(duration-min(30.0,duration))/2); return start,min(duration,start+30.0)

def render_short(source: Path, output: Path, start: float, end: float):
    run(['ffmpeg','-y','-ss',f'{start:.3f}','-i',str(source),'-t',f'{end-start:.3f}','-map','0:v:0','-map','0:a?','-vf','scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','128k','-movflags','+faststart','-shortest',str(output)])

def main():
    parser=argparse.ArgumentParser(description='Create a vertical short with FFmpeg'); parser.add_argument('--url',required=True); parser.add_argument('--output',default='final_short.mp4'); args=parser.parse_args()
    require_ffmpeg(); output=Path(args.output).resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shorts-pipeline-') as tmp:
        source=download_video(args.url,Path(tmp)); duration=get_duration(source)
        if duration <= 0: raise RuntimeError('Could not determine video duration')
        print(f'Source duration: {duration:.1f}s',flush=True); segments=transcribe(source); print(f'Transcript segments: {len(segments)}',flush=True)
        start,end=select_clip(segments,duration)
        if end-start < 1: raise RuntimeError('Selected clip is too short')
        print(f'Rendering {start:.2f}s–{end:.2f}s',flush=True); render_short(source,output,start,end)
    print(f'Created: {output}',flush=True)

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError as exc: print(f'Command failed ({exc.returncode})',file=sys.stderr); sys.exit(exc.returncode or 1)
    except Exception as exc: print(f'Pipeline error: {exc}',file=sys.stderr); sys.exit(1)
