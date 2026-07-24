#!/usr/bin/env python3
"""Render demo/narration-script.md to voice-over audio.

    python3 demo/generate-voiceover.py --check              # what can this machine do?
    python3 demo/generate-voiceover.py --dry-run            # timings only
    python3 demo/generate-voiceover.py                      # macOS `say`
    python3 demo/generate-voiceover.py --engine openai      # neural, expressive
    python3 demo/generate-voiceover.py --engine watson      # IBM neural, expressive

One audio file per scene plus a full track, written to demo/voiceover/. Per-scene
files are the useful ones: each is cut against its own screen recording, so a scene
can be re-recorded without re-rendering the whole video.

## Why the default sounds robotic

macOS ships two generations of voice. The stock set — Alex, Samantha, Fred, Victoria
— predates neural synthesis. They differ in timbre but share one flat, uniform
prosody model, which is why swapping between them changes the voice without changing
the delivery. They cannot be tuned into sounding expressive.

Three ways out, cheapest first:

1. `--engine say` after downloading a Premium voice. Free, offline, a large jump.
   System Settings > Accessibility > Spoken Content > System Voice > Manage Voices,
   then download Ava, Zoe, Evan or Serena (Premium). Run --check to confirm.
2. `--engine openai`. Genuinely expressive and directable — the --tone flag is
   passed to the model as delivery instruction. Needs OPENAI_API_KEY. The whole
   script is a few thousand characters, so a full render costs cents.
3. `--engine watson`. IBM's expressive neural voices. Needs WATSON_TTS_APIKEY and
   WATSON_TTS_URL from an IBM Cloud Text to Speech service credential. Worth
   preferring for this particular demo: the narration says the platform runs on IBM
   models, and a client will notice if the voice-over does too.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_TIMESTAMP = re.compile(r"^##\s*\[(\d{2}:\d{2})\]\s*(.+?)\s*$")
_EMPHASIS = re.compile(r"\*([^*]+)\*")
# Sentence boundary: terminator + space + capital, without splitting "e.g." or "0.72".
# The optional asterisk lets a sentence open with an *emphasized* word.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=\*?[A-Z])")
_WORDS_PER_MINUTE = 145

_PAUSE_SENTENCE_MS = 340
_PAUSE_PARAGRAPH_MS = 650


# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------

def parse_sections(script: Path) -> list[tuple[str, str, str]]:
    """Return (timestamp, title, narration) per scene, in document order."""
    sections: list[tuple[str, str, str]] = []
    timestamp = title = None
    collecting = False
    buffer: list[str] = []

    def flush() -> None:
        if timestamp and buffer:
            sections.append((timestamp, title or "", " ".join(buffer).strip()))

    for raw in script.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        heading = _TIMESTAMP.match(raw)
        if heading:
            flush()
            timestamp, title = heading.group(1), heading.group(2)
            buffer, collecting = [], False
            continue
        if line.startswith("NARRATION:"):
            collecting = True
            remainder = line[len("NARRATION:"):].strip()
            if remainder:
                buffer.append(remainder)
            continue
        if collecting:
            if not line or line.startswith(("**", "#", "---")):
                collecting = False
                continue
            buffer.append(line)
    flush()
    return sections


def plain_text(narration: str) -> str:
    """Narration with authoring markup removed — what a neural engine should read."""
    return _EMPHASIS.sub(r"\1", narration)


def say_markup(narration: str) -> str:
    """Narration with macOS speech commands for pacing and stress.

    A whole scene handed to `say` as one string is read as an unbroken monotone
    run. Explicit inter-sentence silence is the single biggest improvement
    available to the stock voices, because it restores the breathing room a
    reader would take naturally.
    """
    # Split before converting emphasis: the conversion prefixes "[[emph +]]", and a
    # sentence starting with an emphasized word would then no longer begin with a
    # capital, so the boundary — and its pause — would be silently lost.
    sentences = [s.strip() for s in _SENTENCE.split(narration) if s.strip()]
    spoken = [_EMPHASIS.sub(r"[[emph +]]\1[[emph -]]", s) for s in sentences]
    joiner = f" [[slnc {_PAUSE_SENTENCE_MS}]] "
    return joiner.join(spoken)


def estimate_seconds(narration: str) -> float:
    words = len(plain_text(narration).split())
    sentences = max(1, len(_SENTENCE.split(narration)))
    speech = words / _WORDS_PER_MINUTE * 60
    return speech + sentences * _PAUSE_SENTENCE_MS / 1000


def measure_seconds(stem: Path) -> float | None:
    """Actual duration of a rendered file, or None if it cannot be read.

    Estimates assume 145 wpm, but every engine and voice has its own native
    pacing — macOS voices run nearer 175 — so a planning estimate can be a
    minute out over a five-minute script. Measuring closes that gap.
    """
    for suffix in (".m4a", ".mp3"):
        candidate = stem.with_suffix(suffix)
        if not candidate.exists():
            continue
        result = subprocess.run(
            ["afinfo", str(candidate)], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "duration" in line.lower():
                match = re.search(r"([\d.]+)\s*sec", line)
                if match:
                    return float(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def installed_say_voices() -> list[str]:
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    return [line.split("  ")[0].strip() for line in result.stdout.splitlines() if line.strip()]


def premium_say_voices() -> list[str]:
    return [v for v in installed_say_voices() if "(Premium)" in v or "(Enhanced)" in v]


def render_say(text: str, destination: Path, args: argparse.Namespace) -> None:
    command = ["say", "-v", args.voice]
    if args.rate:
        command += ["-r", str(args.rate)]
    command += ["-o", str(destination.with_suffix(".m4a")), say_markup(text)]
    subprocess.run(command, check=True)


def render_openai(text: str, destination: Path, args: argparse.Namespace) -> None:
    from openai import OpenAI

    client = OpenAI()
    payload = {
        "model": args.model or "gpt-4o-mini-tts",
        "voice": args.voice,
        "input": plain_text(text),
    }
    if args.tone:
        payload["instructions"] = args.tone
    try:
        with client.audio.speech.with_streaming_response.create(**payload) as response:
            response.stream_to_file(destination.with_suffix(".mp3"))
    except TypeError:
        # Older models reject `instructions`; the voice still renders without it.
        payload.pop("instructions", None)
        with client.audio.speech.with_streaming_response.create(**payload) as response:
            response.stream_to_file(destination.with_suffix(".mp3"))


def render_watson(text: str, destination: Path, args: argparse.Namespace) -> None:
    import httpx

    api_key = os.environ.get("WATSON_TTS_APIKEY")
    service_url = os.environ.get("WATSON_TTS_URL")
    if not api_key or not service_url:
        raise SystemExit(
            "Watson needs WATSON_TTS_APIKEY and WATSON_TTS_URL. Both come from the\n"
            "service credentials of an IBM Cloud Text to Speech instance."
        )
    response = httpx.post(
        f"{service_url.rstrip('/')}/v1/synthesize",
        params={"voice": args.voice},
        headers={"Content-Type": "application/json", "Accept": "audio/mp3"},
        json={"text": plain_text(text)},
        auth=("apikey", api_key),
        timeout=120.0,
    )
    response.raise_for_status()
    destination.with_suffix(".mp3").write_bytes(response.content)


ENGINES = {
    "say": (render_say, "Samantha"),
    "openai": (render_openai, "onyx"),
    "watson": (render_watson, "en-US_MichaelExpressive"),
}


# ---------------------------------------------------------------------------
# Readiness report
# ---------------------------------------------------------------------------

def report_readiness() -> int:
    print("\nVoice-over engine readiness\n")

    premium = premium_say_voices()
    if premium:
        print("  say     ready — premium voices installed:")
        for voice in premium:
            print(f"            {voice}")
        print("          run with: --engine say --voice \"" + premium[0] + '"')
    else:
        print("  say     usable, but NO premium voice is installed.")
        print("          Only the pre-neural stock voices are available, which is why")
        print("          Alex and Samantha both sound flat. To fix, open:")
        print("            System Settings > Accessibility > Spoken Content")
        print("            > System Voice > Manage Voices")
        print("          Download Ava, Zoe, Evan or Serena (Premium), then re-run --check.")

    if os.environ.get("OPENAI_API_KEY"):
        print("\n  openai  ready — OPENAI_API_KEY is set.")
        print("          run with: --engine openai --voice onyx")
    else:
        print("\n  openai  not configured — set OPENAI_API_KEY.")
        print("          Most expressive option, and --tone directs the delivery.")

    if os.environ.get("WATSON_TTS_APIKEY") and os.environ.get("WATSON_TTS_URL"):
        print("\n  watson  ready — credentials are set.")
        print("          run with: --engine watson --voice en-US_MichaelExpressive")
    else:
        print("\n  watson  not configured — set WATSON_TTS_APIKEY and WATSON_TTS_URL.")
        print("          IBM neural voices; keeps the whole demo on IBM services.")

    print()
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--script", type=Path, default=repo_root / "demo/narration-script.md")
    parser.add_argument("--out", type=Path, default=repo_root / "demo/voiceover")
    parser.add_argument("--engine", choices=sorted(ENGINES), default="say")
    parser.add_argument("--voice", help="engine-specific; default depends on --engine")
    parser.add_argument("--model", help="openai only, e.g. gpt-4o-mini-tts or tts-1-hd")
    parser.add_argument(
        "--tone",
        default=(
            "Confident, warm and measured — a senior engineer walking a client through "
            "something they built and believe in. Vary the pacing: land the opening "
            "lines slowly, pick up through the technical middle, and slow down again "
            "for the closing question. Never breathless, never bored."
        ),
        help="openai only: delivery direction passed to the model",
    )
    parser.add_argument("--rate", type=int, help="say only: words per minute, omit for native")
    parser.add_argument("--dry-run", action="store_true", help="report timings, write nothing")
    parser.add_argument("--check", action="store_true", help="report engine readiness and exit")
    parser.add_argument(
        "--text",
        action="store_true",
        help="print clean narration for pasting into any external TTS service",
    )
    args = parser.parse_args()

    if args.check:
        return report_readiness()

    if args.text:
        for _, title, narration in parse_sections(args.script):
            print(f"# {title}\n")
            print(plain_text(narration))
            print()
        return 0

    render, default_voice = ENGINES[args.engine]
    if not args.voice:
        args.voice = default_voice

    if not args.script.exists():
        print(f"Script not found: {args.script}", file=sys.stderr)
        return 1

    sections = parse_sections(args.script)
    if not sections:
        print("No NARRATION: blocks found — nothing to render.", file=sys.stderr)
        return 1

    if args.engine == "say" and not premium_say_voices() and not args.dry_run:
        print(
            "  NOTE: no premium voice installed — output will sound synthetic.\n"
            "        Run --check for how to fix that before recording.\n"
        )

    if not args.dry_run:
        args.out.mkdir(parents=True, exist_ok=True)

    total_words = 0
    total_estimated = 0.0
    total_measured = 0.0
    measured_all = True
    full_text: list[str] = []

    for index, (timestamp, title, narration) in enumerate(sections, start=1):
        words = len(plain_text(narration).split())
        estimated = estimate_seconds(narration)
        total_words += words
        total_estimated += estimated
        full_text.append(narration)

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        stem = args.out / f"{index:02d}-{slug or 'scene'}"
        line = f"  [{timestamp}] {title:<44} {words:>4}w  ~{estimated:5.1f}s"

        if args.dry_run:
            print(line)
            continue

        render(narration, stem, args)
        actual = measure_seconds(stem)
        if actual is None:
            measured_all = False
            print(f"{line}   (rendered)")
        else:
            total_measured += actual
            print(f"{line}   actual {actual:5.1f}s")

    if not args.dry_run:
        joiner = f" [[slnc {_PAUSE_PARAGRAPH_MS}]] " if args.engine == "say" else "\n\n"
        render(joiner.join(full_text), args.out / "full-narration", args)

    reference = total_measured if (not args.dry_run and measured_all) else total_estimated
    label = "measured" if reference is total_measured else f"estimated at {_WORDS_PER_MINUTE} wpm"
    minutes, seconds = divmod(round(reference), 60)
    print(f"\n  Total: {total_words} words, {minutes}m{seconds:02d}s ({label})")

    if not 4 * 60 + 30 <= reference <= 5 * 60 + 30:
        if reference < 4 * 60 + 30:
            print(f"  Under target. Slow the delivery: --rate {_WORDS_PER_MINUTE}")
        else:
            print("  Over target — trim the script or raise --rate.")

    if not args.dry_run:
        print(f"  Engine: {args.engine} / {args.voice}")
        print(f"  Audio:  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
