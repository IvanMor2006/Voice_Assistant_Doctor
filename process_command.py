import threading, queue

from commands import Commands
from config import similar, COMMAND_THRESHOLD
from state import State

class Process_command(Commands):
    def __init__(self, doctor):
        super().__init__(doctor)
        self.__running = False
        self.__queue = queue.Queue()
        self.__thread = threading.Thread(target=self.__worker)
        self.__lock = threading.Lock()

    def run(self):
        self.__running = True
        self.__thread.start()

    def stop(self):
        self.__running = False
        self.command = None
        if threading.current_thread() != self.__thread and self.__thread:
            self.__thread.join()

    @property
    def command(self):
        return self.__queue.get(timeout=2)

    @command.setter
    def command(self, text):
        self.__queue.put(text)

    def __worker(self):
        while self.__running:
            try:
                text = self.command
                if text is None:
                    break
                with self.__lock:
                    self.__process_command(text)
            except queue.Empty:
                continue

    def __process_command(self, text: str):
        if self.doctor.state in (State.LISTENING_COMMAND, State.LISTENING_KEYWORD):
            self.doctor.state = State.PROCESSING_COMMAND
        
        if (new_state := self.__new_state(text)) != None:
            self.doctor.state = new_state
            return
        
        if self.__command(text):
            if self.doctor.state != State.NOT_RUNNING:
                self.doctor.state = State.LISTENING_KEYWORD
            return

        if answer := self.ollama_query(text):
            self.doctor.speaker.speak(answer)
            self.doctor.state = State.LISTENING_KEYWORD
            return

        self.doctor.state = State.LISTENING_KEYWORD

    def __command(self, text: str) -> bool:
        if text in self.COMMANDS:
            self.COMMANDS[text]()
            return True
        for command in self.COMMANDS:
            if command in text or similar(command, text) > COMMAND_THRESHOLD:
                self.COMMANDS[command]()
                return True
        return False

    def __new_state(self, text: str) -> State | None:
        new_state = self.doctor.state
        for keywords in self.KEYWORDS:
            for keyword in keywords:
                if keyword in text:
                    idx = text.find(keyword) + len(keyword)
                    text = text[idx:].strip()
                    new_state = self.KEYWORDS[keywords]
                    if not text:
                        self.doctor.speaker.speak(self.KEYWORD_COMMANDS[new_state][0])
                        return new_state
        if new_state != State.PROCESSING_COMMAND:
            self.doctor.state = State.PROCESSING_COMMAND
            self.KEYWORD_COMMANDS[new_state][1](text)
            return State.LISTENING_KEYWORD
        return None