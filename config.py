import webbrowser, os
from pynput.keyboard import Key
from datetime import datetime
from rapidfuzz import fuzz
from pathlib import Path

import pywinctl as pwc
import win32gui
import win32process
import psutil

from state import State

def log(text: str, state: str = 'INFO'):
    time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    buf = f'[{time}] [{state}] {text}'
    print(buf)
    if state != 'DEBUG':
        with open(Paths.LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(buf + '\n')

def similar(str1: str, str2: str):
    return fuzz.ratio(str1.lower(), str2.lower()) / 100

def get_windows():
    def enum_callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    windows.append({
                        'hwnd': hwnd,
                        'title': title,
                        'pid': pid,
                        'exe': process.exe(),
                        'window': pwc.getWindowsWithTitle(title)[0] if pwc.getWindowsWithTitle(title) else None
                    })
                except:
                    pass
        return True
    windows = []
    win32gui.EnumWindows(enum_callback, windows)
    return windows

def print_windows():
    result = ''
    windows = get_windows()
    for hwnd, info in windows.items():
        result

VOLUME_MUTE_SCALE = 0.2
VOLUME_UNMUTE_STATES = set(list(State)[:State.LISTENING_COMMAND.value - 1])
VOLUME_MUTE_STATES = set(list(State)[State.LISTENING_COMMAND.value - 1:])
COMMAND_THRESHOLD = 0.85

HOTKEYS = {
    ('следующая вкладка', 'следующая страница') : 'ctrl+tab',
    ('предыдущая вкладка', 'предыдущая страница') : 'ctrl+shift+tab',
    ('закрой вкладку', 'закрой страницу') : 'ctrl+W',
    ('обнови вкладку', 'обнови страницу') : 'ctrl+R',
    ('новая вкладка', 'новая страница') : 'ctrl+T',
    ('смени окно',) : 'alt+tab',
    ('закрой окно',) : 'alt+f4',
    ('убей окно',) : 'ctrl+alt+f4',
    ('следующий экран', 'следующий рабочий стол') : 'win+ctrl+right',
    ('предыдущий экран', 'предыдущий рабочий стол') : 'win+ctrl+left',
    ('диспетчер задач',) : 'ctrl+shift+esc',
    ('youtube широкий экран',) : 'T',
    ('youtube полный экран',) : 'F',
    ('полный экран',) : 'f11',
    ('youtube пауза', 'youtube стоп', 'youtube продолжи') : 'space',
    ('пауза', 'стоп', 'продолжи') : Key.media_play_pause,
    ('тишина', 'молчать', 'звук') : Key.media_volume_mute,
    ('дальше',) : Key.media_next,
    ('назад',) : Key.media_previous
}

class Paths:
    PROJECT_DIR = Path(__file__).parent
    LOG_DIR = PROJECT_DIR / 'log'
    LOG_DIR.mkdir(exist_ok=True)
    DATA_DIR = PROJECT_DIR / 'data'
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR = DATA_DIR / 'cache'
    CACHE_DIR.mkdir(exist_ok=True)

    LOG_PATH = str(LOG_DIR / 'doctor.log')
    BEEP_PATH = str(DATA_DIR / 'beep.mp3')
    SPEAK_PATH = str(DATA_DIR / 'speak.mp3')
    CACHE_PATH = DATA_DIR / 'cache.json'

    LISTEN_ICON_PATH = str(DATA_DIR / 'listen.ico')
    NOT_LISTEN_ICON_PATH = str(DATA_DIR / 'not_listen.ico')

    CACHE_MAX_SIZE = 100
    CACHE_MAX_DAYS = 7

    KEYWORD_PATH = DATA_DIR / 'Doctor_en_windows_v4_0_0.ppn'

    VSCODE_PATH = r'C:/Programms/Microsoft VS Code/Code.exe'

    BROWSER_NAME = 'yandex'
    BROWSER_PATH = r'C:/Users/ivan_/AppData/Local/Yandex/YandexBrowser/Application/browser.exe'
    webbrowser.register(BROWSER_NAME, None, webbrowser.BackgroundBrowser(BROWSER_PATH))

    def __build_program_index(paths):
        index = {}
        for path in paths:
            if not os.path.exists(path):
                log(f'Путь не существует: {path}', 'WARNING')
                continue
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.lnk') or file.lower().endswith('.exe'):
                        name = os.path.splitext(file)[0].lower()
                        index[name] = os.path.join(root, file)
        return index
    
    PROGRAMS = __build_program_index({
        r'C:/Users/ivan_/AppData/Roaming/Microsoft/Windows/Start Menu/Programs',
        r'C:/ProgramData/Microsoft/Windows/Start Menu/Programs',
        r'C:\Users\ivan_\OneDrive\Desktop',
        r'C:\Program Files',
        r'C:\Program Files (x86)',
        r'C:\Programms'
    })  

class Weather:
    URL = r'https://www.gismeteo.by/weather-gomel-4918/'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

class Porcupine:
    ACCESS_KEY = '9YSFHzsZMxbnpCYP/s7HD+Oxhhk/3u9vgOR7Ik54N0BIqBamkTfPrA=='
    SENSITIVITY = 0.55

class Listen:
    SILENCE_THRESHOLD = 300
    RMS_LENGTH_MAX = 150
    INIT_TIMEOUT = 5.0
    END_TIMEOUT = 1.0
    MAX_TIMEOUT = 10.0

class Ollama:
    MODEL = 'gpt-oss:120b-cloud'
    HOST = 'http://localhost:11434'
    TIMEOUT = 10
    HISTORY = {}
    OPEN_PROMPT = f'''
У тебя несколько форматов ответа:
1. OPEN WEBSITE ссылка на веб-сайт
2. OPEN название_программы

Список программ, которые установлены в системе:
{Paths.PROGRAMS.keys()}
Если есть что-то похожее на программу из этого списка, то ответ должен быть формата 2.
Если это не программа из списка, то найди соответствующий веб-сайт и отправь на него ссылку в формате ответа 1.
Если я попросил расписание, то пиши OPEN WEBSITE file:///D:/Labs/Расписание.pdf
Если я попросил переводчик, то пиши OPEN WEBSITE https://neuro-translate

Запрос:
'''
    @property
    def CLOSE_WINDOW_PROMPT():
        return f'''
Если есть что-то похожее на окно из этого списка (смотри поля 'title' и 'exe'), то ответ должен состоять только из hwnd нужного окна.

Список открытых окон на данный момент:
{get_windows()}

Запрос:
'''
    SYSTEM_PROMPT = '''
Ты — Доктор, голосовой помощник, интегрированный в систему. Твой хозяин — Иван.

Твоя задача — отвечать на вопросы и поддерживать беседу, когда встроенные команды не распознаны. Вот что важно:

### ОТВЕТЫ
- Русский язык.
- Больше конкретики (если на вопрос можно ответить одним предложением, отвечай).
- Максимум 2–3 предложения (для голосового вывода).
- Разговорный, дружелюбный стиль, можно с лёгким юмором, если уместно.
- Если вопрос сложный или требует развёрнутого ответа, предложи поискать информацию в интернете.
- Если не знаешь ответа, честно признайся и предложи помощь.

### ЧЕГО ИЗБЕГАТЬ
- Лишних и бессмысленных разговоров. (Пример: "Если нужно с чем-то помочь, дай знать!").
- Длинных монологов и технических подробностей.
- Неуверенных слов («как бы», «типа», «вроде»).
- Эмодзи, сокращений («т.к.», «т.е.»), аббревиатур и спецсимволов — они плохо озвучиваются.
- Ответов на несуществующие вопросы или домыслов.
- Различных лишних символов по типу **текст** - они плохо озвучиваются.

### ДОПОЛНИТЕЛЬНО
- Если пользователь просто здоровается («привет», «доброе утро»), ответь приветствием (можно использовать имя, если оно известно).
- Старайся, чтобы ответы были полезными и по делу.
'''