# Голосовой помощник «Доктор»

Голосовой ассистент с пробуждением по ключевому слову, интеграцией локальной LLM и управлением системой.

## Возможности

- Пробуждение по ключевому слову (Porcupine)
- Распознавание речи (Google Speech API)
- Интеграция с локальной LLM (Ollama)
- Озвучивание ответов (Edge TTS) с кэшированием
- Управление системой:
  - Громкость и яркость
  - Горячие клавиши
  - Закрытие окон через Win32 API
  - Выключение/перезагрузка/сон
- Трей-иконка с меню

## Технологии

- Python 3.10+
- asyncio, threading, queue
- speech_recognition, edge-tts
- pvporcupine, pyaudio
- ollama, requests
- pycaw, pynput, pyautogui, win32gui
- pystray, PIL

## Установка

```bash
# Клонирование репозитория
git clone https://github.com/ваш-username/voice-assistant-doctor.git
cd voice-assistant-doctor

# Установка зависимостей
pip install -r requirements.txt

# Запуск
python doctor.py
```