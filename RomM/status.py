import itertools
import threading
from typing import Optional

from models import Collection, Platform, Rom


class View:
    PLATFORMS = "platform"
    COLLECTIONS = "collection"
    VIRTUAL_COLLECTIONS = "virtual_collection"
    ROMS = "roms"
    SAVES = "saves"
    STATES = "states"


class Filter:
    ALL = "all"
    LOCAL = "local"
    REMOTE = "remote"


class Status:
    _instance: Optional["Status"] = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Status, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self.valid_host = True
        self.valid_credentials = True

        self.me = None
        self.profile_pic_path = ""

        self.current_view: str = View.PLATFORMS
        self.selected_platform: Optional[Platform] = None
        self.selected_collection: Optional[Collection] = None
        self.selected_virtual_collection: Optional[Collection] = None
        self.selected_save: Optional["SaveData"] = None
        self.selected_state: Optional["StateSave"] = None

        self.show_start_menu = False
        self.show_contextual_menu = False

        self.platforms: list[Platform] = []
        self.collections: list[Collection] = []
        self.roms: list[Rom] = []
        self.roms_to_show: list[Rom] = []
        self.saves: list["SaveData"] = []
        self.saves_to_show: list["SaveData"] = []
        self.states: list["StateSave"] = []
        self.states_to_show: list["StateSave"] = []
        self.filters = itertools.cycle([Filter.ALL, Filter.LOCAL, Filter.REMOTE])
        self.current_filter = next(self.filters)

        self.platforms_ready = threading.Event()
        self.collections_ready = threading.Event()
        self.roms_ready = threading.Event()
        self.saves_ready = threading.Event()
        self.states_ready = threading.Event()
        self.download_rom_ready = threading.Event()
        self.abort_download = threading.Event()
        self.me_ready = threading.Event()
        self.updating = threading.Event()

        # Initialize events what won't launch at startup
        self.roms_ready.set()
        self.saves_ready.set()
        self.states_ready.set()
        self.download_rom_ready.set()
        self.abort_download.set()

        self.multi_selected_roms: list[Rom] = []
        self.download_queue: list[Rom] = []
        self.downloading_rom: Optional[Rom] = None
        self.downloading_rom_position = 0
        self.total_downloaded_bytes = 0
        self.downloaded_percent = 0.0
        self.extracting_rom = False
        self.extracted_percent = 0.0

    def reset_roms_list(self) -> None:
        self.roms = []

    def reset_saves_list(self) -> None:
        self.saves = []

    def reset_states_list(self) -> None:
        self.states = []
