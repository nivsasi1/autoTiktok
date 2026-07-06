import random

import config


def build_caption(story, niche: str, rng=None) -> str:
    """Title (trimmed at a word boundary) + fixed hashtags + 2 rotating."""
    rng = rng or random
    title = story.title
    if len(title) > config.CAPTION_TITLE_CHARS:
        cut = title[: config.CAPTION_TITLE_CHARS]
        idx = cut.rfind(" ")
        title = (cut[:idx] if idx > 0 else cut).rstrip() + "…"
    tags = config.HASHTAGS[niche]
    chosen = tags["fixed"] + rng.sample(tags["pool"], 2)
    return f"{title} {' '.join(chosen)}"
