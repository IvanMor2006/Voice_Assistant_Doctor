import subprocess, threading, pystray, queue, os
from PIL import Image

from config import Paths

class TrayIcon:
    def __init__(self, doctor):
        self.doctor = doctor
        self.__running = False
        self.__queue = queue.Queue()
        self.__thread = threading.Thread(target=self.__worker, daemon=True)
        
        def clear_log():
            with open(Paths.LOG_PATH, 'w') as f:
                pass
        def stop_ass():
            self.doctor.process_command.command = 'не подслушивай'
        def restart_ass():
            self.doctor.process_command.command = 'почисти уши'
        
        menu = pystray.Menu(
            pystray.MenuItem('Открыть в VS Code', lambda: subprocess.Popen([Paths.VSCODE_PATH, Paths.PROJECT_DIR])),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Открыть log', lambda: os.startfile(Paths.LOG_PATH)),
            pystray.MenuItem('Очистить log', clear_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Перезапустить', restart_ass),
            pystray.MenuItem('Выход', stop_ass)
        )
        image = Image.open(Paths.NOT_LISTEN_ICON_PATH)
        self.__icon = pystray.Icon('Doctor_Icon', image, 'Голосовой помощник', menu)

    def run(self):
        self.__running = True
        self.__thread.start()
        self.__icon.run()

    def stop(self):
        self.__icon.stop()
        self.__running = False
        self.__queue.put(None)
        if threading.current_thread() != self.__thread and self.__thread:
            self.__thread.join(timeout=2)

    def set_image(self, image_path):
        self.__queue.put(Image.open(image_path))

    def __worker(self):
        while self.__running:
            try:
                image = self.__queue.get(timeout=2)
                if image is None:
                    break
                self.__icon.icon = image
            except queue.Empty:
                continue