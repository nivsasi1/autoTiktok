import json
import requests
import wave
import contextlib
import subprocess
import subtitles

headers = {
    "Accept" : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent" : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Accept-Language" : "en-US,en;q=0.9",
    "Sec-Fetch-Dest" : "document",
}

AUDIO_FILE_PATH = "outputw.wav"
SUBTITLES_FILE_PATH = "subtitles.srt"
TRANSCRIPT_FILE_PATH = "transcript.srt"
INPUT_VID_FILE_PATH = "vid.mp4"

def main():
    js = getRedditPost(0, 1) 
    print(js)
    subtitles.analyzeRedditPost(js)
    generateAudioFile(js, AUDIO_FILE_PATH)
    exportVideo()

def exportVideo():
    #ffmpeg 
    # -i 
    # vid.mp4
    # -i 
    # outputw.wav 
    # -filter_complex 
    # "fps=60,scale=1080x1920:force_original_aspect_ratio=increase,crop=1080:1920:1080:40,subtitles='subtitles.srt':force_style='FontName=PT Sans,Alignment=10,Outline=0,OutlineColour=&H100000000,Shadow=0,Fontsize=18,MarginL=20,MarginV=25'" 
    # -shortest 
    # -c:v 
    # h264_videotoolbox 
    # -b:v 
    # 1000k 
    # -map 1  
    # out3.mp4
    subprocess.call(['ffmpeg',
                    '-y',
                    '-i',
                    INPUT_VID_FILE_PATH,
                    '-i',
                    AUDIO_FILE_PATH,
                    '-filter_complex', 
                    "scale=1080x1920:force_original_aspect_ratio='increase',crop='1080:1920:1080:40',subtitles='subtitles.srt':force_style='FontName=PT Sans,Bold=1,Alignment=10,Outline=0,OutlineColour=&H100000000,Shadow=0,Fontsize=20,MarginL=20,MarginV=25'",
                    '-shortest',
                    '-c:v',
                    'h264_videotoolbox',
                    '-b:v',
                    '1000k',
                    '-map',
                    '1',
                    'out3.mp4'
                     ])

def getRedditPost(index: int, amount: int):
    if(index >= amount):
        return ""
    url = f'https://www.reddit.com/r/stories/new.json?sort=new&limit={amount}'
    json_data = requests.get(url, headers=headers)
    js = json.loads(json_data.text)["data"]["children"][index]["data"]["selftext"]
    return js

# larynx -v southern_english_female-glow_tts --length-scale 1 -q "high" 
def generateAudioFile(content: str, toDir: str):
    output_audio = open(toDir, "w")
    subprocess.call(['larynx','-v',"southern_english_female-glow_tts", content,"--length-scale","1","-q","high"], stdout=output_audio)

def getAudioLength(fileName: str):
    with contextlib.closing(wave.open(fileName,'r')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)
        return duration 

main()
# exportVideo()