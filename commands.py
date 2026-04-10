import pygetwindow as gw, webbrowser, subprocess, pyautogui, requests, keyboard, ollama, time, sys, os
from screen_brightness_control import get_brightness, set_brightness
from pynput.keyboard import Key, Controller
from bs4 import BeautifulSoup
from datetime import datetime
from winsound import Beep

import win32gui, win32con

from config import log, get_windows, HOTKEYS, Paths, Weather, Ollama
from state import State

class Commands:
    __keyboard = Controller()
    def __init__(self, doctor):
        self.doctor = doctor
        self.COMMANDS = {
            'ничего' : lambda: None,
            'не подслушивай' : self.__stop_ass,
            'почисти уши' : self.__restart_ass,
            'завершение работы' : self.__stop_sys,
            'перезагрузка' : self.__restart_sys,
            'режим сна' : self.__sleep_sys,

            'какая яркость': lambda: self.doctor.speaker.speak(f'Яркость. {get_brightness()}%'),
            'ярче' : lambda: set_brightness('+25'),
            'темнее' : lambda: set_brightness('-25'),
            'какая громкость': lambda: self.doctor.speaker.speak(f'Громкость. {int(self.doctor.volume.level * 100)}%'),
            'громче' : lambda: self.__set_volume_level(self.doctor.volume.level + 0.20),
            'тише' : lambda: self.__set_volume_level(self.doctor.volume.level - 0.20),
            'сколько времени' : lambda: self.doctor.speaker.speak(datetime.now().strftime('%H:%M')),
            'погода сейчас' : self.weather_now,
            'погода на сегодня' : self.weather_today,
            
            **{f'{word} {value}{suffix}' : lambda w=word,v=value: set_brightness(v) if w == 'яркость' else self.__set_volume_level(v / 100)
               for word in ['яркость', 'громкость']
               for value in range(0, 101, 1)
               for suffix in ['', '%']},
            
            **{name : lambda k=key: [self.__hotkey(k)]
                for names, key in HOTKEYS.items()
                    for name in names}
        }
        self.KEYWORDS = {
            ('пиши', 'напиши', 'запиши', 'введи') : State.TYPING,
            ('закрой окно',) : State.CLOSING_WINDOW,
            ('заверши процесс', 'убей окно', 'убей процесс') : State.CLOSING_PROCESS,
            ('включи', 'открой', 'запусти') : State.OPENING,
            ('найди в youtube', 'найди в ютуби', 'поищи в youtube', 'поищи в ютуби') : State.SEARCHING_YOUTUBE,
            ('найди', 'поищи') : State.SEARCHING
        }
        self.KEYWORD_COMMANDS = {
            State.TYPING : ['Что написать?', self.type],
            State.CLOSING_WINDOW : ['Что закрыть?', self.close_window],
            State.CLOSING_PROCESS : ['ЧТо завершить?', self.close_process],
            State.OPENING : ['Что открыть?', self.open],
            State.SEARCHING_YOUTUBE : ['Что найти?', self.search_youtube],
            State.SEARCHING : ['Что найти?', self.search_google]
        }

    def __stop(self, text: str):
        self.doctor.speaker.speak(text)
        time.sleep(2)
        self.doctor.stop()
        self.doctor.tray_icon.stop()
        log('Завершение работы доктора\n', 'END')
    def __stop_ass(self):
        self.__stop('До свидания')
        sys.exit(0)
    def __restart_ass(self):
        self.__stop('Не прощаюсь')
        subprocess.Popen([sys.executable] + sys.argv)
    def __stop_sys(self):
        self.__stop('Выключаю')
        for _ in range(4):
            Beep(500, 250)
            time.sleep(0.75)
        Beep(500, 1000)
        os.system("shutdown /s /t 0")
    def __restart_sys(self):
        self.__stop('Перезагружаю')
        for _ in range(5):
            if _ == 2:
                Beep(500, 1000)
                time.sleep(0.75)
                continue
            Beep(500, 250)
            time.sleep(0.75)
        os.system("shutdown /r /t 0")
    def __sleep_sys(self):
        self.doctor.speaker.speak('Усыпляю')
        for _ in range(5):
            Beep(500, 250)
            time.sleep(0.75)
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    def __set_volume_level(self, value: int):
        log(f'Меняю громкость командой с {self.doctor.volume.level} на {value}', 'DEBUG')
        self.doctor.volume.level = value
        Beep(500, 500)

    def weather_now(self):
        try:
            response = requests.get(Weather.URL, headers=Weather.HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            weathertab = soup.find('a', class_='weathertab')

            weather_feel = weathertab.find('div', class_='weather-value')
            temp_real = weather_feel.find('temperature-value')['value']

            weather_feel = weathertab.find('div', class_='weather-feel')
            temp_feel = weather_feel.find('temperature-value')['value']

            self.doctor.speaker.speak(f'Сейчас {weathertab["data-tooltip"]}. Температура {temp_real} градуса по Цельсию. По ощущению {temp_feel}')
        except:
            self.doctor.speaker.speak('Не удалось найти')

    def weather_today(self):
        try:
            response = requests.get(Weather.URL, headers=Weather.HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            weathertab = soup.find('div', class_='weathertab is-active')

            temp_today = weathertab.find_all('temperature-value')
            temp_values = []
            for temp in temp_today:
                temp_values.append(temp['value'])
            
            self.doctor.speaker.speak(f'Сегодня {weathertab["data-tooltip"]}. Температура от {temp_values[0]} до {temp_values[1]} градусов по Цельсию')
        except:
            self.doctor.speaker.speak('Не удалось найти')

    def __hotkey(self, key: Key | str):
        window: gw.Win32Window = gw.getActiveWindow()
        if not window.isActive:
            window.activate()
        if isinstance(key, Key):
            self.__keyboard.press(key)
            self.__keyboard.release(key)
        elif '+' in key:
            keyboard.send(key)
        else:
            pyautogui.press(key)

    def type(self, text: str):
        keyboard.write(text + ' ')
    def close_window(self, text: str):
        if hwnd := self.ollama_query(Ollama.CLOSE_WINDOW_PROMPT() + text):
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                self.doctor.speaker.speak('Закрываю окно')
            except Exception as e:
                log(f'Ошибка в close_window: {e}', 'ERROR')
                self.doctor.speaker.speak('Ошибка при закрытии окна')
    def close_process(self, text: str):
        pass
    def open(self, text: str):
        if answer := self.ollama_query(Ollama.OPEN_PROMPT() + text):
            try:
                if (keyword := 'OPEN WEBSITE') in answer:
                    idx = answer.find(keyword) + len(keyword)
                    url = answer[idx:].strip()
                    self.doctor.speaker.speak('Открываю')
                    webbrowser.get(Paths.BROWSER_NAME).open(url)
                    return
                elif (keyword := 'OPEN') in answer:
                    idx = answer.find(keyword) + len(keyword)
                    program_name = answer[idx:].strip()
                    self.doctor.speaker.speak('Запускаю')
                    os.startfile(Paths.PROGRAMS()[program_name])
                    return
                raise Exception('неправильный формат сообщения от Ollama')
            except Exception as e:
                log(f'Ошибка в open: {e}', 'ERROR')
                self.doctor.speaker.speak('Ошибка при открытии')
    def __search(self, url: str):
        self.doctor.speaker.speak('Вот что удалось найти')
        webbrowser.get(Paths.BROWSER_NAME).open(url)
    def search_youtube(self, text: str):
        url = rf'https://www.youtube.com/results?search_query={text.replace(" ", "+")}'
        self.__search(url)
    def search_google(self, text: str):
        url = rf'https://www.google.com/search?q={text.replace(" ", "+")}&sourceid=chrome&ie=UTF-8&safe=strict'
        self.__search(url)
    def ollama_query(self, text: str) -> str | None:
        try:
            client = ollama.Client(host=Ollama.HOST)
            self.doctor.speaker.speak('Думаю')
            response = client.generate(
                model=Ollama.MODEL,
                system=Ollama.SYSTEM_PROMPT + f'### ИСТОРИЯ ОБЩЕНИЯ = {Ollama.HISTORY if len(Ollama.HISTORY) != 0 else "пуста"}',
                prompt=text,
                options={'timeout' : Ollama.TIMEOUT}
            )
            answer = response['response']
            log(f'Ollama ответ: {answer}')
            Ollama.HISTORY['Хозяин: ' + text] = 'Голосовой помощник: ' + answer
            if len(Ollama.HISTORY) > 10:
                first_mes = next(iter(Ollama.HISTORY))
                Ollama.HISTORY.pop(first_mes)
            return answer
        except Exception as e:
            log(f'Ошибка Ollma: {e}', 'ERROR')
            self.doctor.speaker.speak('Произошла ошибка в Ollama')
            return None