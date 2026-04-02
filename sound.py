import threading, edge_tts, asyncio, getpass, hashlib, queue, time, uuid, json, os, re
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from datetime import datetime
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from pygame import mixer
from pathlib import Path

from config import log, Paths
from state import State

class Volume:
    __devices = AudioUtilities.GetSpeakers()
    __interface = __devices._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    __volume = __interface.QueryInterface(IAudioEndpointVolume)
    def __init__(self):
        self.__lock = threading.RLock()
        self.__last_level = self.level
        self.__muted = False
    
    @property
    def last_level(self):
        with self.__lock:
            return self.__last_level
    
    @last_level.setter
    def last_level(self, level):
        with self.__lock:
            self.__last_level = max(0.0, min(1.0, level))

    @property
    def level(self):
        with self.__lock:
            return self.__volume.GetMasterVolumeLevelScalar()

    @level.setter
    def level(self, level):
        with self.__lock:
            old = self.level
            self.last_level = old
            self.__volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level)), None)

    @property
    def muted(self):
        with self.__lock:
            return self.__muted
        
    @muted.setter
    def muted(self, value):
        with self.__lock:
            self.__muted = value

class Sound:
    def __init__(self, doctor):
        mixer.init()
        self.stopped = False
        self.__beep = mixer.Sound(Paths.BEEP_PATH)
        self.__play_count = 0
        self.__lock = threading.Lock()

        self.doctor = doctor

    def __del__(self):
        mixer.quit()

    @property
    def play_count(self):
        with self.__lock:
            return self.__play_count

    def play_sound(self, sound_path: str | mixer.Sound):
        if self.doctor.volume.muted == True:
            self.doctor.volume.level = self.doctor.volume.last_level

        if isinstance(sound_path, str):
            sound = mixer.Sound(sound_path)
        else:
            sound = sound_path
        sound.set_volume(0.5)

        with self.__lock:
            self.__play_count += 1
        channel = sound.play()
        while channel.get_busy():
            if self.doctor.state == State.LISTENING_COMMAND:
                self.stopped = True
                sound.stop()
                break
            time.sleep(0.05)
        with self.__lock:
            self.__play_count -= 1

        if self.doctor.volume.muted == True and self.stopped == False:
            self.doctor.volume.level = self.doctor.volume.last_level

    def play_beep(self):
        self.play_sound(self.__beep)

class Speaker:
    def __init__(self, sound: Sound):
        self.__running = False
        self.__gen_queue = queue.Queue()
        self.__play_queue = queue.Queue()
        self.__gen_thread = threading.Thread(target=self.__gen_worker)
        self.__play_thread = threading.Thread(target=self.__play_worker)
        
        self.__cache = {}
        self.__load_cache()

        self.sound = sound

    def run(self):
        self.__running = True
        self.__gen_thread.start()
        self.__play_thread.start()
        self.speak(f'Добрый день {getpass.getuser()}')

    def stop(self):
        self.__running = False
        self.__gen_queue.put(None)
        self.__play_queue.put(None)
        if threading.current_thread() != self.__gen_thread and self.__gen_thread:
            self.__gen_thread.join()
        if threading.current_thread() != self.__play_thread and self.__play_thread:
            self.__play_thread.join()

        self.__save_cache()

    def speak(self, text: str):
        if self.__running:
            raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            sentences = [s.strip() for s in raw_sentences if s.strip()]
            for s in sentences:
                self.__gen_queue.put(s)

    def __gen_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.__running:
            try:
                text = self.__gen_queue.get(timeout=2)
                if text is None:
                    break
                if self.sound.stopped == False:
                    cache_path = self.__get_cache_path(text)
                    if cache_path:
                        log(f'Использую кэш для: \'{text}\'', 'DEBUG')
                        self.__play_queue.put(cache_path)
                    else:
                        loop.run_until_complete(self.__generate(text))
                elif self.__gen_queue.empty() and self.__play_queue.empty():
                    self.sound.stopped = False
            except queue.Empty:
                continue
        loop.close()
            
    async def __generate(self, text):
        tts = edge_tts.Communicate(text, 'ru-RU-DmitryNeural')
        speak_path = Paths.CACHE_DIR / f'speak_{uuid.uuid4()}.mp3'
        await tts.save(speak_path)

        self.__add_to_cache(text, speak_path)

        self.__play_queue.put(str(speak_path))

    def __play_worker(self):
        while self.__running:
            try:
                sound_path = self.__play_queue.get(timeout=2)
                if sound_path is None:
                    break
                if self.sound.stopped == False:
                    self.sound.play_sound(sound_path)
                elif self.__gen_queue.empty() and self.__play_queue.empty():
                    self.sound.stopped = False
            except queue.Empty:
                continue

    def __load_cache(self):
        if Paths.CACHE_PATH.exists():
            try:
                with open(Paths.CACHE_PATH, 'r', encoding='utf-8') as f:
                    self.__cache = json.load(f)
            except Exception as e:
                log(f'Ошибка загрузки кэша: {e}', 'ERROR')
                self.__cache = {}

    def __save_cache(self):
        try:
            with open(Paths.CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.__cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f'Ошибка сохранения кэша: {e}', 'ERROR')

    def __get_cache_key(self, text: str) -> str:
        normalized = ' '.join(text.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def __get_cache_path(self, text: str) -> str | None:
        cache_key = self.__get_cache_key(text)

        if cache_key in self.__cache:
            cache_info = self.__cache[cache_key]

            cache_file = cache_info.get('file')
            cache_path = Paths.CACHE_DIR / cache_file

            if cache_path.exists():
                self.__cache[cache_key] = {
                    'file': cache_file,
                    'text': text,
                    'last_used': datetime.now().isoformat()
                }
                return str(cache_path)
            else:
                del self.__cache[cache_key]
        return None
    
    def __add_to_cache(self, text: str, file_path: Path):
        cache_key = self.__get_cache_key(text)
        cache_file = file_path.name

        self.__cache[cache_key] = {
            'file': cache_file,
            'text': text,
            'last_used': datetime.now().isoformat()
        }

        if len(self.__cache) > Paths.CACHE_MAX_SIZE:
            self.__cleanup_cache(force=True)

        self.__save_cache()

    def __cleanup_cache(self, force=False):
        try:
            current_time = datetime.now()
            files_to_delete = []
            cache_items = list(self.__cache.items())

            cache_items.sort(key=lambda x: x[1].get('last_used', '2000-01-01'))

            for cache_key, cache_info in cache_items:
                cache_file = Paths.CACHE_DIR / cache_info['file']

                if cache_file.exists():
                    file_age = current_time - datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_age.days > Paths.CACHE_MAX_DAYS:
                        files_to_delete.append((cache_key, cache_file))
                else:
                    files_to_delete.append((cache_key, None))

            for cache_key, cache_file in files_to_delete:
                if cache_file and cache_file.exists():
                    try:
                        cache_file.unlink()
                    except Exception as e:
                        log(f'Ошибка при удалении файла {cache_file}: {e}', 'ERROR')
                del self.__cache[cache_key]

            if force and (excess := len(self.__cache) - Paths.CACHE_MAX_SIZE) > 0:
                for cache_key, cache_info in cache_items[:excess]:
                    cache_file = Paths.CACHE_DIR / cache_info['file']
                    if cache_file.exists():
                        try:
                            cache_file.unlink()
                        except Exception as e:
                            log(f'Ошибка при удалении файла {cache_file}: {e}', 'ERROR')
                    del self.__cache[cache_key]
            
            self.__save_cache()
            log(f'Очистка кэша завершена, осталось {len(self.__cache)} записей', 'DEBUG')

        except Exception as e:
            log(f'Ошибка при очистке кэша: {e}', 'ERROR')