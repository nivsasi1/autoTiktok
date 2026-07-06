import config
from sources.base import (ContentSource, Story, clean_text, fetch_entries,
                          html_to_text)

LISTING_URL = "https://www.reddit.com/r/{subs}/hot.rss?limit=50"


def qualifies(entry, used_ids) -> bool:
    # RSS has no over_18/stickied flags: filter AutoModerator + NSFW title tags
    title = (entry.title or "").lower()
    return (entry.kind == "t3"
            and entry.id not in used_ids
            and entry.author.lower() != "/u/automoderator"
            and "nsfw" not in title)   # tag can appear anywhere in the title


def build_script(title: str, body: str, outro: str) -> str:
    if title and title[-1] not in ".!?":
        title += "."
    return f"{title} {body} {outro}"


class RedditTextSource(ContentSource):
    """Selftext-post source; drama and horror niches differ only by preset."""

    def __init__(self, niche: str, preset, used_ids: set[str]):
        self.niche = niche
        self.preset = preset
        self.used_ids = used_ids

    def fetch(self) -> Story | None:
        url = LISTING_URL.format(subs="+".join(self.preset.subreddits))
        for entry in fetch_entries(url):
            if not qualifies(entry, self.used_ids):
                continue
            body = clean_text(html_to_text(entry.html), config.MAX_CHARS)
            if len(body) < config.MIN_CHARS:
                continue
            title = clean_text(entry.title, 300)
            return Story(
                id=entry.id,
                title=title,
                text=build_script(title, body, self.preset.outro),
                url=entry.link,
                niche=self.niche,
            )
        return None
