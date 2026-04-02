import speech_recognition as sr, pvporcupine, subprocess, threading, requests, pyaudio, struct, numpy as np, math, time

from config import log, VOLUME_MUTE_SCALE, VOLUME_MUTE_STATES, VOLUME_UNMUTE_STATES, Paths, Porcupine, Listen, Ollama
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

        self.volume = Volume()
        self.sound = Sound(self)
        self.speaker = Speaker(self.sound)
        self.process_command = Process_command(self)
        self.tray_icon = TrayIcon(self)
        log('Успешно', 'START')
        
    def run(self):
        self.state = State.LISTENING_KEYWORD
        self.__thread.start()
        self.speaker.run()
        self.process_command.run()
        self.tray_icon.run()
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

    def __worker(self):
        porcupine = pvporcupine.create(
            access_key=Porcupine.ACCESS_KEY,
            keyword_paths=[Paths.KEYWORD_PATH],
            sensitivities=[Porcupine.SENSITIVITY]
        )
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length
        )
        command_buffer = []
        rms_arr = []
        last_voice_time = time.time()
        speech_start_time = last_voice_time
        speech_detected = False
        while self.state != State.NOT_RUNNING:
            try:
                pcm_bytes = audio_stream.read(porcupine.frame_length)
            except Exception as e:
                log(f'Ошибка чтения аудио', 'ERROR')
                break
            
            pcm = struct.unpack_from('h' * porcupine.frame_length, pcm_bytes)

            rms = self.__compute_rms(pcm)

            if rms < Listen.SILENCE_THRESHOLD * 2:
                rms_arr.append(rms)
            if len(rms_arr) > Listen.RMS_LENGTH_MAX:
                Listen.SILENCE_THRESHOLD = max(50, np.mean(rms_arr) * 2)
                log(f'Порог тишины {Listen.SILENCE_THRESHOLD}', 'DEBUG')
                rms_arr = rms_arr[Listen.RMS_LENGTH_MAX // 2:]

            if self.state == State.LISTENING_KEYWORD:
                if porcupine.process(pcm) >= 0:
                    log('Обнаружено ключевое слово')
                    
                    self.sound.play_beep()

                    self.state = State.LISTENING_COMMAND
                    last_voice_time = time.time()
                    speech_start_time = last_voice_time
                    speech_detected = False

                    for _ in range(10):
                        audio_stream.read(porcupine.frame_length)
                    command_buffer.clear()

            elif self.state == State.PROCESSING_COMMAND:
                time.sleep(0.01)
                continue
            else:
                if self.sound.play_count > 0:
                    time.sleep(0.01)
                    continue

                if rms > Listen.SILENCE_THRESHOLD:
                    log(f'RMS: {rms}', 'DEBUG')
                    
                command_buffer.append(pcm_bytes)
                if rms > Listen.SILENCE_THRESHOLD:
                    speech_detected = True
                    last_voice_time = time.time()
                else:
                    if not speech_detected:
                        if time.time() - last_voice_time >= Listen.INIT_TIMEOUT:
                            log('Таймаут ожидания речи, возврат к ключевому слову')
                            command_buffer.clear()
                            self.state = State.LISTENING_KEYWORD
                    elif time.time() - last_voice_time >= Listen.END_TIMEOUT or (max_timeout := (time.time() - speech_start_time >= Listen.MAX_TIMEOUT)):
                        if max_timeout:
                            log('Таймаут макмимальной длины речи')
                        log(f'Команда записана, длина: {len(command_buffer)} блоков', 'DEBUG')
                        full_audio = b''.join(command_buffer)
                        text = self.__transcribe(full_audio, porcupine.sample_rate)
                        if text:
                            self.process_command.command = text
                        command_buffer.clear()
                        last_voice_time = time.time()
                        speech_start_time = last_voice_time
                        speech_detected = False
        audio_stream.stop_stream()
        audio_stream.close()
        pa.terminate()
        porcupine.delete()

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
            log('Речь не распознана', 'WARNING')
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