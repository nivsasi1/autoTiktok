import config
from sources.base import (ContentSource, Story, clean_text, fetch_entries,
                          html_to_text)
from sources.reddit_text import build_script


class RedditUrlSource(ContentSource):
    """A single pasted Reddit post URL; the picked niche's preset supplies
    voice, caption style and outro. Raises ValueError with a friendly reason
    instead of returning None — the user chose this exact post."""

    def __init__(self, url: str, preset, niche: str):
        self.url = url
        self.preset = preset
        self.niche = niche

    def fetch(self) -> Story:
        url = (self.url or "").split("?")[0].split("#")[0].strip().rstrip("/")
        if "reddit.com" not in url or "/comments/" not in url:
            raise ValueError("that doesn't look like a reddit post URL "
                             "(expected .../r/<sub>/comments/<id>/...)")
        # a post's own .rss feed: first t3 entry is the post, t1s are comments
        entries = fetch_entries(url + ".rss?limit=1")
        post = next((e for e in entries if e.kind == "t3"), None)
        if post is None:
            raise ValueError("couldn't read that post from reddit — is the "
                             "URL right and the post still up?")
        body = clean_text(html_to_text(post.html or ""), config.MAX_CHARS)
        if len(body) < 50:
            raise ValueError("that post has no story text (a link/image "
                             "post?) — pick a selftext post")
        title = clean_text(post.title, 300)
        return Story(id=post.id, title=title,
                     text=build_script(title, body, self.preset.outro),
                     url=post.link, niche=self.niche)
