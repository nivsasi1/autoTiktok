import math

TRANSCRIPT_FILE_PATH = "transcript.srt"
SUBTITLES_FILE_PATH = "subtitles.srt"

def resertFiles():
    file = open(SUBTITLES_FILE_PATH, "w")
    file.write('')
    file.close()

def analyzeRedditPost(content: str):
    resertFiles()
    file = open(TRANSCRIPT_FILE_PATH, "w")
    file.write(content)
    file.close()
    makeSubtitles(TRANSCRIPT_FILE_PATH)

def makeSubtitles(file_path):
    file = open(file_path, "r")
    last_time = 0
    subtitle_written = 1
    while True:
        line = file.readline()
        if not line:
            break
        words = line.split(" ")
        duration = 0
        word_count = 0
        content = ''
        DOT_BREAK = 0.21
        for (index, word) in enumerate(words):
            word.replace("'","")
            word_count += 1
            word_duration = calculateWordDuration(word)
            duration += word_duration
            
            if(word_count > 4 or index == (len(words) - 1) or "," in word or "." in word):
                #If it's the beginning of a new line and it's a dot or a semi (,.) it can be skipped
                isadot = "." in word
                print(f"word count:{word_count}")
                print(f"word length:{len(word)}")
                if(len(word) == 1 and word_count == 1):
                    if(isadot):
                        last_time += DOT_BREAK
                    duration = 0
                    word_count = 0
                    print("a dot or semi!")
                    continue
                if(isadot):
                    duration += DOT_BREAK
                exportToFile(subtitle_written, content + word, last_time, last_time + duration)
                subtitle_written += 1
                last_time += duration
                word_count = 0
                duration = 0
                content = ''
                continue

            content += word + ' '

def exportToFile(uid, content, start, end):
    file = open(SUBTITLES_FILE_PATH, "a") 
    timestamp = convertToSrt(start, end)
    data = f"{uid}\n{timestamp}\n{content}\n"
    print(data)
    file.write(data)

def convertToSrt(start, end):
    print(f"seconds: {start}")
    p1 = convertToHMSMS(start)#timedelta(seconds= start * 1000)
    p2 = convertToHMSMS(end)#timedelta(seconds= start * 1000)
    return f"{p1} --> {p2}"

def convertToHMSMS(seconds):
    ms = int(seconds * 1000 % 1000)
    s = int(seconds % 60)
    m = int(seconds / 60)
    h = 0
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def calculateWordDuration(word):
    wc = len(word)
    duration = 0.17
    if wc > 3:
       sc = syllableCount(word)
       #duration = word_length / 3 * 0.175
       duration = ((wc - sc) / 3) * 0.175 + sc * 0.18 / 3
    if wc > 10:
        duration = wc / 3 * 0.185
    return duration 

def syllableCount(word):
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if word[0] in vowels:
        count += 1
    for index in range(1, len(word)):
        if word[index] in vowels and word[index - 1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if count == 0:
        count += 1
    return count
