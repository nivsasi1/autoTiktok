import hashlib

import config
from sources.base import ContentSource, Story, clean_text
from sources.reddit_text import build_script


class FreeformSource(ContentSource):
    """Pasted title + story text; id is a text hash so used-id tracking works
    without a real post behind it."""

    def __init__(self, title: str, text: str, preset, niche: str):
        self.title = title
        self.text = text
        self.preset = preset
        self.niche = niche

    def fetch(self) -> Story:
        title = clean_text(self.title or "", 300)
        body = clean_text(self.text or "", config.MAX_CHARS)
        if not title:
            raise ValueError("give the story a title")
        if len(body) < 50:
            raise ValueError("story text is too short to narrate "
                             "(need at least ~50 characters)")
        digest = hashlib.sha1(f"{title}\n{body}".encode("utf-8")).hexdigest()
        return Story(id=f"freeform-{digest[:10]}", title=title,
                     text=build_script(title, body, self.preset.outro),
                     url="", niche=self.niche)
