import asyncio

import edge_tts

from subtitles import WordBoundary

_TICKS_PER_SECOND = 10_000_000  # edge-tts offsets are 100-ns ticks


async def _synthesize(text: str, audio_path: str, voice: str) -> list[WordBoundary]:
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    boundaries: list[WordBoundary] = []
    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / _TICKS_PER_SECOND
                end = (chunk["offset"] + chunk["duration"]) / _TICKS_PER_SECOND
                boundaries.append(WordBoundary(chunk["text"], start, end))
    return boundaries


def synthesize(text: str, audio_path: str, voice: str) -> list[WordBoundary]:
    """Speak `text` into `audio_path` (mp3); return real word timings."""
    boundaries = asyncio.run(_synthesize(text, audio_path, voice))
    if not boundaries:
        raise RuntimeError("edge-tts returned no word boundaries — is the "
                           "voice name valid and the network up?")
    return boundaries
