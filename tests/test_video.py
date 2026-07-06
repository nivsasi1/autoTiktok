from video import build_cmd


def test_build_cmd_maps_filtered_video_and_audio():
    cmd = build_cmd("vid.mp4", "output.mp3", "subtitles.srt", "out.mp4",
                    bg_offset=12.5)
    joined = " ".join(cmd)
    assert cmd[0] == "ffmpeg"
    assert "-ss 12.50" in joined          # seek before the video input
    assert joined.index("-ss") < joined.index("vid.mp4")
    assert "[0:v]" in joined and "[v]" in joined
    assert "-map [v] -map 1:a" in joined  # video from filter, audio from mp3
    assert "libx264" in joined
    assert "subtitles=subtitles.srt" in joined
    assert cmd[-1] == "out.mp4"
