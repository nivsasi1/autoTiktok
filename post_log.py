import json


def append_post(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_posts(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            posts = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    posts.append(json.loads(line))
                except ValueError:   # tolerate a corrupt line
                    continue
            return posts
    except OSError:
        return []
