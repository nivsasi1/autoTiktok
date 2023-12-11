# autoTiktok
auto pulling story, making audio, then adding on a minecraft video with subtitles, and uploading to tiktok automatically

## larynx installation
```
python3 -m venv larynx_venv
source larynx_venv/bin/activate

pip3 install --upgrade pip
pip3 install --upgrade wheel setuptools

pip3 install -f 'https://synesthesiam.github.io/prebuilt-apps/' -f 'https://download.pytorch.org/whl/cpu/torch_stable.html' larynx
```

## ffmpeg installation
```
https://github.com/BtbN/FFmpeg-Builds/releases
```

## python dependencies
```
pip3 install requests
pip3 install wave
```

-------------
### How to use?
make sure you have the following files in the project directory:
* video file - vid.mp4
https://www.youtube.com/watch?v=Pt5_GSKIWQM (10min Minecraft parkour with no copyright)

run the command
```
python3 ./main.py
```

The program generates 3 files:
1. voice audio file - outputw.wav
2. subtitles file - subtitles.srt
3. video file - out.mp4

**DO NOT delete any of these files in the proccess**

