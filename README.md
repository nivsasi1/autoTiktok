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

-------------
#How to use?
run the command
```
python3 ./main.py
```
