from enum import Enum, auto
class State(Enum):
    NOT_RUNNING = auto()
    PROCESSING_COMMAND = auto()
    LISTENING_KEYWORD = auto()
    
    LISTENING_COMMAND = auto()
    TYPING = auto()
    CLOSING_WINDOW = auto()
    CLOSING_PROCESS = auto()
    OPENING = auto()
    SEARCHING_YOUTUBE = auto()
    SEARCHING = auto()