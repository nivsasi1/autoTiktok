import config
from sources.base import (ContentSource, Story, clean_text, fetch_entries,
                          html_to_text)

LISTING_URL = "https://www.reddit.com/r/AskReddit/hot.rss?limit=25"


def usable_comment(entry) -> bool:
    # feed order ≈ best ranking; RSS exposes no scores
    return (entry.kind == "t1"
            and entry.author.lower() not in ("", "/u/automoderator")
            and bool((entry.html or "").strip()))


def build_script(title: str, answers: list[str], outro: str,
                 max_chars=config.MAX_CHARS) -> str:
    if title and title[-1] not in ".!?":
        title += "?"  # AskReddit titles are questions
    script = title
    budget = max_chars - len(outro) - 1
    for i, answer in enumerate(answers, 1):
        piece = f" Number {i}. {answer}"
        if len(script) + len(piece) > budget:
            break
        script += piece
    return f"{script} {outro}"


class AskRedditSource(ContentSource):
    """Question + top comments assembled into a list-style script."""

    def __init__(self, preset, used_ids: set[str]):
        self.preset = preset
        self.used_ids = used_ids

    def fetch(self) -> Story | None:
        for post in fetch_entries(LISTING_URL):
            if (post.kind != "t3" or post.id in self.used_ids
                    or post.author.lower() == "/u/automoderator"):
                continue
            comments = fetch_entries(post.link.rstrip("/") + "/.rss?limit=25")
            answers = []
            for c in comments:  # feed order ≈ best ranking
                if not usable_comment(c):
                    continue
                body = clean_text(html_to_text(c.html),
                                  config.ASKREDDIT_MAX_ANSWER_CHARS)
                if len(body) < 20 or body.lower() in ("deleted", "removed"):
                    continue
                answers.append(body)
                if len(answers) == config.ASKREDDIT_MAX_ANSWERS:
                    break
            if len(answers) < 3:  # not enough for a list video
                continue
            title = clean_text(post.title, 300)
            return Story(
                id=post.id,
                title=title,
                text=build_script(title, answers, self.preset.outro),
                url=post.link,
                niche="askreddit",
            )
        return None
