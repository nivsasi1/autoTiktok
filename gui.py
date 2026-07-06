"""Phase C GUI: render with a click, paste a Reddit URL or freeform text,
preview before posting. Run with `python gui.py` (local only)."""

import contextlib
import io
import queue
import threading
from dataclasses import replace
from types import SimpleNamespace

import gradio as gr

import config
import metadata
import pending
import pipeline
from main import _park_part2, _publish, build_source
from sources.base import load_used_ids, record_used_id
from sources.freeform import FreeformSource
from sources.reddit_url import RedditUrlSource

PRESET_VOICE = "preset default"
VOICES = [PRESET_VOICE] + sorted({p.voice for p in config.NICHES.values()} |
                                 {"en-US-JennyNeural", "en-GB-RyanNeural"})


def _build_story(mode, niche, url, title, text):
    preset = config.NICHES[niche]
    if mode == "reddit url":
        return RedditUrlSource(url, preset, niche).fetch()
    if mode == "freeform":
        return FreeformSource(title, text, preset, niche).fetch()
    used = load_used_ids(config.STATE_PATH)
    story = build_source(niche, preset, used).fetch()
    if story is None:
        raise ValueError(f"no qualifying {niche} post right now — "
                         "try again later or paste a URL")
    return story


def do_render(mode, niche, url, title, text, voice):
    """Generator: streams status lines while a worker thread renders."""
    logq = queue.Queue()
    box = {}

    def work():
        try:
            story = _build_story(mode, niche, url, title, text)
            logq.put(f"story: {story.title}")
            preset = config.NICHES[niche]
            if voice != PRESET_VOICE:
                preset = replace(preset, voice=voice)
            box["result"] = pipeline.render_story(story, preset, niche,
                                                  log=logq.put)
            box["story"] = story
        except Exception as exc:
            box["error"] = str(exc)
        finally:
            logq.put(None)

    threading.Thread(target=work, daemon=True).start()
    lines = ["rendering — first run of a long story takes a few minutes…"]
    pend = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
    while (item := logq.get()) is not None:
        lines.append(item)
        yield ("\n".join(lines), *pend)

    if "error" in box:
        # clear the state so a stale previous render can't be posted by mistake
        yield (f"error: {box['error']}", *pend[:4], None)
        return

    story, result = box["story"], box["result"]
    # freeform has no feed to collide with; auto/url record like the CLI
    if not story.id.startswith("freeform-"):
        try:
            record_used_id(config.STATE_PATH, story.id)
        except OSError as exc:
            lines.append(f"warning: couldn't update {config.STATE_PATH} ({exc})")
    part_of = {p: path for path, p in result.videos}
    split = result.split
    cap1 = metadata.build_caption(story, niche, part=1 if split else None)
    cap2 = metadata.build_caption(story, niche, part=2) if split else ""
    state = {"id": story.id, "title": story.title, "url": story.url,
             "niche": niche, "split": split}
    lines.append("done — preview below, tweak the caption, then post")
    yield ("\n".join(lines),
           gr.update(value=part_of.get(1) or result.videos[0][0]),
           gr.update(value=part_of.get(2), visible=split),
           gr.update(value=cap1),
           gr.update(value=cap2, visible=split),
           state)


def do_post(state, cap1, cap2, account, dry_run):
    if not state:
        return "render something first"
    if not account:
        return "pick an account"
    acc_niche = config.ACCOUNTS[account].niche
    if acc_niche != state["niche"]:
        return (f"'{account}' posts {acc_niche}, but this render is "
                f"{state['niche']} — pick a matching account")
    story = SimpleNamespace(id=state["id"], title=state["title"],
                            url=state["url"])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if state["split"]:
            if dry_run:
                print(f"dry-run: would queue {config.OUTPUT_PART2_PATH} "
                      "for the next scheduled run")
            else:
                pending.enqueue(config.QUEUE_DIR, config.OUTPUT_PART2_PATH,
                                {"story_id": story.id, "part": 2,
                                 "account": account, "niche": state["niche"],
                                 "title": story.title, "url": story.url,
                                 "caption": cap2})
                print("queued part 2 — the next scheduled --post run sends it")
            rc = _publish(story, account, dry_run, part=1, caption=cap1)
            if rc != 0 and not dry_run:
                _park_part2(story.id)
        else:
            _publish(story, account, dry_run, caption=cap1)
    return out.getvalue().strip()


def _toggle_inputs(mode):
    return (gr.update(visible=mode == "reddit url"),
            gr.update(visible=mode == "freeform"),
            gr.update(visible=mode == "freeform"))


def build_app():
    with gr.Blocks(title="autoTiktok") as app:
        gr.Markdown("# autoTiktok\nRender a story video, preview it, post it.")
        mode = gr.Radio(["auto", "reddit url", "freeform"], value="auto",
                        label="Source", info="auto pulls the niche's subreddits")
        url_in = gr.Textbox(label="Reddit post URL", visible=False,
                            placeholder="https://www.reddit.com/r/nosleep/comments/…")
        title_in = gr.Textbox(label="Title", visible=False)
        text_in = gr.TextArea(label="Story text", visible=False, lines=8)
        with gr.Row():
            niche_dd = gr.Dropdown(sorted(config.NICHES),
                                   value=config.DEFAULT_NICHE, label="Niche")
            voice_dd = gr.Dropdown(VOICES, value=PRESET_VOICE, label="Voice")
        render_btn = gr.Button("Render", variant="primary")
        status = gr.Textbox(label="Status", lines=8, interactive=False)
        with gr.Row():
            with gr.Column():
                vid1 = gr.Video(label="Part 1", interactive=False)
                cap1 = gr.Textbox(label="Caption", lines=2)
            with gr.Column():
                vid2 = gr.Video(label="Part 2", interactive=False,
                                visible=False)
                cap2 = gr.Textbox(label="Caption (part 2)", lines=2,
                                  visible=False)
        with gr.Row():
            account_dd = gr.Dropdown(sorted(config.ACCOUNTS), label="Account")
            dry = gr.Checkbox(value=True, label="Dry run (never uploads)")
            post_btn = gr.Button("Post")
        post_status = gr.Textbox(label="Post result", interactive=False)
        story_state = gr.State()

        mode.change(_toggle_inputs, mode, [url_in, title_in, text_in])
        render_btn.click(do_render,
                         [mode, niche_dd, url_in, title_in, text_in, voice_dd],
                         [status, vid1, vid2, cap1, cap2, story_state])
        post_btn.click(do_post, [story_state, cap1, cap2, account_dd, dry],
                       post_status)
    return app


if __name__ == "__main__":
    build_app().launch(server_name="127.0.0.1", inbrowser=True)
