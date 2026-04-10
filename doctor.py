import speech_recognition as sr, subprocess, threading, requests, pyaudio, queue, struct, numpy as np, math, time

from config import log, VOLUME_MUTE_SCALE, VOLUME_MUTE_STATES, VOLUME_UNMUTE_STATES, Paths, WakeWord, Listen, Ollama
from process_command import Process_command
from sound import Volume, Sound, Speaker
from state import State
from tray_icon import TrayIcon

def ensure_ollama_running():
    try:
        response = requests.get(Ollama.HOST + '/api/tags', timeout=2)
        if response.status_code == 200:
            log('Ollama уже запущен', 'INFO')
            return True
    except requests.exceptions.RequestException:
        pass

    log('Ollama не отвечает. Запускаем сервер...', 'WARNING')
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(
            ['ollama', 'serve'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        time.sleep(5)

        for _ in range(10):
            try:
                requests.get(Ollama.HOST + '/api/tags', timeout=2)
                log('Ollama успешно запущен', 'START')
                return True
            except:
                time.sleep(1)
        log('Не удалось запустить Ollama', 'WARNING')
        return False
    except FileNotFoundError:
        log('Команда \'ollama\' не найдена. Убедитесь, что Ollama установлена и доступна в PATH', 'WARNING')
        return False

class Doctor:
    def __init__(self):
        log('Инициализация доктора...', 'START')

        ensure_ollama_running()

        self.__state = State.NOT_RUNNING
        self.__state_lock = threading.Lock()
        self.__thread = threading.Thread(target=self.__worker)
        self.__recognizer = sr.Recognizer()
        self.__recognizer.energy_threshold = Listen.SILENCE_THRESHOLD
        self.__trancsribe_queue = queue.Queue()
        self.__wake_word_thread = threading.Thread(target=self.__transcribe_worker)

        self.volume = Volume()
        self.sound = Sound(self)
        self.speaker = Speaker(self.sound)
        self.process_command = Process_command(self)
        self.tray_icon = TrayIcon(self)
        log('Успешно', 'START')
        
    def run(self):
        self.state = State.LISTENING_KEYWORD
        self.__thread.start()
        self.__wake_word_thread.start()
        self.speaker.run()
        self.process_command.run()
        self.tray_icon.run()
        self.__wake_word_thread.join()
        self.__thread.join()
        self.tray_icon.stop()
        self.process_command.stop()
        self.speaker.stop()

    def stop(self):
        self.state = State.NOT_RUNNING

    @property
    def state(self):
        with self.__state_lock:
            return self.__state
    
    @state.setter
    def state(self, value):
        if self.__state == value:
            return
        if value in VOLUME_MUTE_STATES and self.volume.muted == False:
            self.volume.level = self.volume.level * VOLUME_MUTE_SCALE
            self.volume.muted = True
            log(f'Замутил звук с {self.volume.last_level} на {self.volume.level}', 'DEBUG')
            self.tray_icon.set_image(Paths.LISTEN_ICON_PATH)
        elif value in VOLUME_UNMUTE_STATES and self.volume.muted == True:
            self.volume.level = self.volume.last_level
            self.volume.muted = False
            log(f'Размутил звук с {self.volume.last_level} на {self.volume.level}', 'DEBUG')
            self.tray_icon.set_image(Paths.NOT_LISTEN_ICON_PATH)
        
        log(f'Меняю состояние со {self.state} на {value}', 'DEBUG')
        with self.__state_lock:
            self.__state = value

    def __transcribe_worker(self):
        while self.state != State.NOT_RUNNING:
            try:
                command_buffer = self.__trancsribe_queue.get(timeout=2)
                full_audio = b''.join(command_buffer)
                text = self.__transcribe(full_audio, WakeWord.SAMPLE_RATE)
                if self.state == State.LISTENING_KEYWORD:
                    if text and WakeWord.KEYWORD in text:
                        log('Обнаружено ключевое слово')
                        self.sound.play_beep()
                        self.state = State.LISTENING_COMMAND
                        while not self.__trancsribe_queue.empty():
                            try:
                                self.__trancsribe_queue.get_nowait()
                            except queue.Empty:
                                break
                        self.__command_buffer.clear()
                        self.start_command_time = time.time()
                else:
                    if text:
                        self.process_command.command = text
                        self.__command_buffer.clear()

            except queue.Empty:
                continue

    def __worker(self):
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=WakeWord.SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=WakeWord.FRAME_LENGTH
        )
        self.__command_buffer = []
        rms_arr = []
        self.start_command_time = None
        self.last_speech_time = None
        while self.state != State.NOT_RUNNING:
            try:
                pcm_bytes = audio_stream.read(WakeWord.FRAME_LENGTH)
            except Exception as e:
                log(f'Ошибка чтения аудио', 'ERROR')
                break
            
            pcm = struct.unpack_from('h' * WakeWord.FRAME_LENGTH, pcm_bytes)
            self.__command_buffer.append(pcm_bytes)
            rms = self.__compute_rms(pcm)
            
            if len(rms_arr) > Listen.RMS_LENGTH_MAX:
                Listen.SILENCE_THRESHOLD = max(50, np.mean(rms_arr) * 2)
                log(f'Порог тишины {Listen.SILENCE_THRESHOLD}', 'DEBUG')
                rms_arr = rms_arr[Listen.RMS_LENGTH_MAX // 2:]
            if rms < Listen.SILENCE_THRESHOLD * 2:
                rms_arr.append(rms)
            # if rms > Listen.SILENCE_THRESHOLD:
            #     log(f'RMS: {rms}', 'DEBUG')
            if self.state == State.LISTENING_KEYWORD:
                if len(self.__command_buffer) % 20 == 0:
                    self.__trancsribe_queue.put(self.__command_buffer[-40:])
            elif self.state == State.PROCESSING_COMMAND:
                time.sleep(0.01)
                continue
            else:
                if self.sound.play_count > 0:
                    time.sleep(0.01)
                    continue
                if rms > Listen.SILENCE_THRESHOLD:
                    self.last_speech_time = time.time()
                if not self.last_speech_time:
                    if self.start_command_time and time.time() - self.start_command_time > Listen.INIT_TIMEOUT:
                        log('Таймаут ожидания речи, возврат к ключевому слову')
                        self.__command_buffer.clear()
                        self.state = State.LISTENING_KEYWORD
                        continue
                elif time.time() - self.last_speech_time > Listen.END_TIMEOUT or (max_timeout := (self.start_command_time and time.time() - self.start_command_time > Listen.MAX_TIMEOUT)):
                    if max_timeout:
                        log('Таймаут макмимальной длины речи')
                    log(f'Команда записана, длина: {len(self.__command_buffer)} блоков', 'DEBUG')
                    self.__trancsribe_queue.put(self.__command_buffer)
                    self.last_speech_time = None
                    self.start_command_time = None
        audio_stream.stop_stream()
        audio_stream.close()
        pa.terminate()

    def __compute_rms(self, pcm):
        if not pcm:
            return 0
        sum_squares = sum(sample * sample for sample in pcm)
        return math.sqrt(sum_squares / len(pcm))
    
    def __transcribe(self, audio_bytes, sample_rate):
        try:
            audio_data = sr.AudioData(
                audio_bytes,
                sample_rate,
                sample_width=2
            )
            text = self.__recognizer.recognize_google(audio_data, language='ru-RU')
            log(f'Распознано: {text}')
            return text.lower()
        except sr.UnknownValueError:
            pass
            # log('Речь не распознана', 'WARNING')
        except sr.RequestError as e:
            log(f'Ошибка сервиса распознавания: {e}', 'ERROR')
        except Exception as e:
            log(f'Ошибка при распознании: {e}', 'ERROR')
        return None
    
def __main__():
    doctor = Doctor()
    doctor.run()

if __name__ == '__main__':
    __main__()