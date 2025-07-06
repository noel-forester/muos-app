import base64
import datetime
import json
import math
import os
import re
import shutil
import zipfile
from typing import Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from filesystem import MUOS_SUPPORTED_PLATFORMS, Filesystem
from imageutils import ImageUtils
from models import Collection, Platform, Rom
from PIL import Image
from status import Status, View
from utils import str_to_bool

# Load .env file from one folder above
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class API:
    _platforms_endpoint = "api/platforms"
    _platform_icon_url = "assets/platforms"
    _collections_endpoint = "api/collections"
    _virtual_collections_endpoint = "api/collections/virtual"
    _roms_endpoint = "api/roms"
    _user_me_endpoint = "api/users/me"
    _user_profile_picture_url = "assets/romm/assets"
    _assets_endpoint = "assets/romm/resources"

    def __init__(self):
        self.host = os.getenv("HOST", "")
        self.username = os.getenv("USERNAME", "")
        self.password = os.getenv("PASSWORD", "")
        self.headers = {}
        self._exclude_platforms = set(self._getenv_list("EXCLUDE_PLATFORMS"))
        self._include_collections = set(self._getenv_list("INCLUDE_COLLECTIONS"))
        self._exclude_collections = set(self._getenv_list("EXCLUDE_COLLECTIONS"))
        self._collection_type = os.getenv("COLLECTION_TYPE", "collection")
        self._download_assets = str_to_bool(os.getenv("DOWNLOAD_ASSETS", "false"))
        self._fullscreen_assets = str_to_bool(os.getenv("FULLSCREEN_ASSETS", "false"))
        self._download_existing_roms = str_to_bool(
            os.getenv("DOWNLOAD_EXISTING_ROMS", "true")
        )

        self._status = Status()
        self._file_system = Filesystem()
        self._image_utils = ImageUtils(640, 480)

        if self.username and self.password:
            credentials = f"{self.username}:{self.password}"
            auth_token = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            self.headers = {"Authorization": f"Basic {auth_token}"}

    @staticmethod
    def _getenv_list(key: str) -> list[str]:
        value = os.getenv(key)
        return [item.strip() for item in value.split(",")] if value is not None else []

    @staticmethod
    def _human_readable_size(size_bytes: int) -> Tuple[float, str]:
        if size_bytes == 0:
            return 0, "B"
        size_name = ("B", "KB", "MB", "GB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return (s, size_name[i])

    def _sanitize_filename(self, filename: str) -> str:
        path_parts = os.path.normpath(filename).split(os.sep)
        sanitized_parts = []

        for _i, part in enumerate(path_parts):
            sanitized = re.sub(r'[\\/*?:"<>|\t\n\r\b]', "_", part)
            sanitized_parts.append(sanitized)

        return os.path.join(*sanitized_parts)

    def _fetch_user_profile_picture(self, avatar_path: str) -> None:
        fs_extension = avatar_path.split(".")[-1]
        try:
            request = Request(
                f"{self.host}/{self._user_profile_picture_url}/{avatar_path}",
                headers=self.headers,
            )
        except ValueError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        try:
            if request.type not in ("http", "https"):
                self._status.valid_host = False
                self._status.valid_credentials = False
                return
            response = urlopen(request, timeout=60)  # trunk-ignore(bandit/B310)
        except HTTPError as e:
            print(e)
            if e.code == 403:
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            else:
                raise
        except URLError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        if not os.path.exists(self._file_system.resources_path):
            os.makedirs(self._file_system.resources_path)
        self._status.profile_pic_path = (
            f"{self._file_system.resources_path}/{self.username}.{fs_extension}"
        )
        with open(self._status.profile_pic_path, "wb") as f:
            f.write(response.read())
        icon = Image.open(self._status.profile_pic_path)
        icon = icon.resize((26, 26))
        icon.save(self._status.profile_pic_path)
        self._status.valid_host = True
        self._status.valid_credentials = True

    def fetch_me(self) -> None:
        try:
            request = Request(
                f"{self.host}/{self._user_me_endpoint}", headers=self.headers
            )
        except ValueError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        try:
            if request.type not in ("http", "https"):
                self._status.valid_host = False
                self._status.valid_credentials = False
                return
            response = urlopen(request, timeout=60)  # trunk-ignore(bandit/B310)
        except HTTPError as e:
            print(e)
            if e.code == 403:
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            else:
                raise
        except URLError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        me = json.loads(response.read().decode("utf-8"))
        self._status.me = me
        if me["avatar_path"]:
            self._fetch_user_profile_picture(me["avatar_path"])
        self._status.me_ready.set()

    def _fetch_platform_icon(self, platform_slug) -> None:
        try:
            request = Request(
                f"{self.host}/{self._platform_icon_url}/{platform_slug}.ico",
                headers=self.headers,
            )
        except ValueError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return

        try:
            if request.type not in ("http", "https"):
                self._status.valid_host = False
                self._status.valid_credentials = False
                return
            response = urlopen(request, timeout=60)  # trunk-ignore(bandit/B310)
        except HTTPError as e:
            print(e)
            if e.code == 403:
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            # Icon is missing on the server
            elif e.code == 404:
                self._status.valid_host = True
                self._status.valid_credentials = True
                return
            else:
                raise
        except URLError as e:
            print(e)
            self._status.valid_host = False
            self._status.valid_credentials = False
            return

        if not os.path.exists(self._file_system.resources_path):
            os.makedirs(self._file_system.resources_path)

        with open(f"{self._file_system.resources_path}/{platform_slug}.ico", "wb") as f:
            f.write(response.read())

        icon = Image.open(f"{self._file_system.resources_path}/{platform_slug}.ico")
        icon = icon.resize((30, 30))
        icon.save(f"{self._file_system.resources_path}/{platform_slug}.ico")
        self._status.valid_host = True
        self._status.valid_credentials = True

    def fetch_platforms(self) -> None:
        try:
            request = Request(
                f"{self.host}/{self._platforms_endpoint}", headers=self.headers
            )
        except ValueError:
            self._status.platforms = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        try:
            if request.type not in ("http", "https"):
                self._status.platforms = []
                self._status.valid_host = False
                self._status.valid_credentials = False
                return
            response = urlopen(request, timeout=60)  # trunk-ignore(bandit/B310)
        except HTTPError as e:
            if e.code == 403:
                self._status.platforms = []
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            else:
                raise
        except URLError:
            self._status.platforms = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        platforms = json.loads(response.read().decode("utf-8"))
        if isinstance(platforms, dict):
            platforms = platforms["items"]
        _platforms: list[Platform] = []
        for platform in platforms:
            if platform["rom_count"] > 0:
                if (
                    platform["slug"].lower() not in MUOS_SUPPORTED_PLATFORMS
                    or platform["slug"] in self._exclude_platforms
                ):
                    continue
                _platforms.append(
                    Platform(
                        id=platform["id"],
                        display_name=platform["display_name"],
                        rom_count=platform["rom_count"],
                        slug=platform["slug"],
                    )
                )
                if not os.path.exists(
                    f"{self._file_system.resources_path}/{platform['slug']}.ico"
                ):
                    self._fetch_platform_icon(platform["slug"])
        _platforms.sort(key=lambda platform: platform.display_name)
        self._status.platforms = _platforms
        self._status.valid_host = True
        self._status.valid_credentials = True
        self._status.platforms_ready.set()

    def fetch_collections(self) -> None:
        try:
            collections_request = Request(
                f"{self.host}/{self._collections_endpoint}", headers=self.headers
            )
            v_collections_request = Request(
                f"{self.host}/{self._virtual_collections_endpoint}?type={self._collection_type}",
                headers=self.headers,
            )
        except ValueError:
            self._status.collections = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return

        try:
            if collections_request.type not in ("http", "https"):
                self._status.collections = []
                self._status.valid_host = False
                self._status.valid_credentials = False
                return

            collections_response = urlopen(  # trunk-ignore(bandit/B310)
                collections_request, timeout=60
            )
            v_collections_response = urlopen(  # trunk-ignore(bandit/B310)
                v_collections_request, timeout=60
            )
        except HTTPError as e:
            if e.code == 403:
                self._status.collections = []
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            else:
                raise
        except URLError:
            self._status.collections = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return

        collections = json.loads(collections_response.read().decode("utf-8"))
        v_collections = json.loads(v_collections_response.read().decode("utf-8"))

        if isinstance(collections, dict):
            collections = collections["items"]
        if isinstance(v_collections, dict):
            v_collections = v_collections["items"]

        _collections: list[Collection] = []

        for collection in collections:
            if collection["rom_count"] > 0:
                if self._include_collections:
                    if collection["name"] not in self._include_collections:
                        continue
                elif self._exclude_collections:
                    if collection["name"] in self._exclude_collections:
                        continue
                _collections.append(
                    Collection(
                        id=collection["id"],
                        name=collection["name"],
                        rom_count=collection["rom_count"],
                        virtual=False,
                    )
                )

        for v_collection in v_collections:
            if v_collection["rom_count"] > 0:
                if self._include_collections:
                    if v_collection["name"] not in self._include_collections:
                        continue
                elif self._exclude_collections:
                    if v_collection["name"] in self._exclude_collections:
                        continue
                _collections.append(
                    Collection(
                        id=v_collection["id"],
                        name=v_collection["name"],
                        rom_count=v_collection["rom_count"],
                        virtual=True,
                    )
                )

        _collections.sort(key=lambda collection: collection.name)

        self._status.collections = _collections
        self._status.valid_host = True
        self._status.valid_credentials = True
        self._status.collections_ready.set()

    def fetch_roms(self) -> None:
        if self._status.selected_platform:
            view = View.PLATFORMS
            id = self._status.selected_platform.id
        elif self._status.selected_collection:
            view = View.COLLECTIONS
            id = self._status.selected_collection.id
        elif self._status.selected_virtual_collection:
            view = View.VIRTUAL_COLLECTIONS
            id = self._status.selected_virtual_collection.id
        else:
            return

        try:
            request = Request(
                f"{self.host}/{self._roms_endpoint}?{view}_id={id}&order_by=name&order_dir=asc",
                headers=self.headers,
            )
        except ValueError:
            self._status.roms = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return
        try:
            if request.type not in ("http", "https"):
                self._status.roms = []
                self._status.valid_host = False
                self._status.valid_credentials = False
                return
            response = urlopen(request, timeout=1800)  # trunk-ignore(bandit/B310)
        except HTTPError as e:
            if e.code == 403:
                self._status.roms = []
                self._status.valid_host = True
                self._status.valid_credentials = False
                return
            else:
                raise
        except URLError:
            self._status.roms = []
            self._status.valid_host = False
            self._status.valid_credentials = False
            return

        roms = json.loads(response.read().decode("utf-8"))
        if isinstance(roms, dict):
            roms = roms["items"]

        _roms = [
            Rom(
                id=rom["id"],
                name=rom["name"],
                summary=rom["summary"],
                fs_name=rom["fs_name"],
                platform_id=rom["platform_id"],
                platform_slug=rom["platform_slug"],
                fs_extension=rom["fs_extension"],
                fs_size=self._human_readable_size(rom["fs_size_bytes"]),
                fs_size_bytes=rom["fs_size_bytes"],
                multi=rom["multi"],
                languages=rom["languages"],
                regions=rom["regions"],
                revision=rom["revision"],
                tags=rom["tags"],
                path_cover_large=rom["path_cover_large"].split("?")[
                    0
                ],  # TODO: safety check?
                path_cover_small=rom["path_cover_small"].split("?")[
                    0
                ],  # TODO: safety check?
                path_screenshot=f"/assets/romm/resources/roms/{rom['platform_id']}/{rom['id']}/screenshots/0.jpg",
                first_release_date=rom["first_release_date"],
                average_rating=rom["average_rating"],
                genres=rom["genres"],
                franchises=rom["franchises"],
                companies=rom["companies"],
                age_ratings=rom["age_ratings"],
            )
            for rom in roms
            if rom["platform_slug"] in MUOS_SUPPORTED_PLATFORMS
        ]

        _roms.sort(key=lambda rom: rom.name)
        self._status.roms = _roms
        self._status.valid_host = True
        self._status.valid_credentials = True
        self._status.roms_ready.set()

    def _reset_download_status(
        self, valid_host: bool = False, valid_credentials: bool = False
    ) -> None:
        self._status.total_downloaded_bytes = 0
        self._status.downloaded_percent = 0
        self._status.valid_host = valid_host
        self._status.valid_credentials = valid_credentials
        self._status.downloading_rom = None
        self._status.extracting_rom = False
        self._status.multi_selected_roms = []
        self._status.download_queue = []
        self._status.download_rom_ready.set()
        self._status.abort_download.set()

    def _download_file(self, url: str, dest_path: str, rom: Rom) -> bool:
        """Download a file with progress tracking and abort capability."""
        print(f"Fetching: {url}")
        request = Request(url, headers=self.headers)

        if request.type not in ("http", "https"):
            print("Invalid URL scheme")
            self._reset_download_status()
            return False

        print(f"Downloading {rom.name} to {dest_path}")

        self._status.total_downloaded_bytes = 0
        self._status.downloaded_percent = 0
        chunk_size = 8192

        with urlopen(request) as response, open(  # trunk-ignore(bandit/B310)
            dest_path, "wb"
        ) as out_file:
            while not self._status.abort_download.is_set():
                chunk = response.read(chunk_size)
                if not chunk:
                    print("Download completed")
                    break

                out_file.write(chunk)

                # Update status
                self._status.valid_host = True
                self._status.valid_credentials = True
                self._status.total_downloaded_bytes += len(chunk)

                # Calculate percentage (avoid division by zero)
                total_size = max(rom.fs_size_bytes, 1)
                self._status.downloaded_percent = (
                    self._status.total_downloaded_bytes / total_size
                ) * 100

            if self._status.abort_download.is_set():
                print("Download aborted")
                self._reset_download_status(True, True)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                return False

        return True

    def _extract_zip_file(self, zip_path: str) -> bool:
        """Extract a ZIP file with progress tracking and abort capability."""
        extract_dir = os.path.dirname(zip_path)
        self._status.extracting_rom = True
        print("Multi-file ROM detected. Extracting...")

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            total_size = sum(file.file_size for file in zip_ref.infolist())
            extracted_size = 0
            self._status.extracted_percent = 0

            for file in zip_ref.infolist():
                if self._status.abort_download.is_set():
                    print("Extraction aborted")
                    self._reset_download_status(True, True)
                    return False

                # Sanitize the full path including all nested directories
                sanitized_filename = self._sanitize_filename(file.filename)
                file_path = os.path.join(extract_dir, sanitized_filename)

                # Handle directory entries
                if file.filename.endswith("/") or file.filename.endswith("\\"):
                    os.makedirs(file_path, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with zip_ref.open(file) as source, open(file_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                extracted_size += file.file_size
                self._status.extracted_percent = (
                    extracted_size / max(total_size, 1)
                ) * 100

        self._status.extracting_rom = False
        return True

    def download_rom(self) -> None:
        self._status.download_queue.sort(key=lambda rom: rom.name)
        for i, rom in enumerate(self._status.download_queue):
            self._status.downloading_rom = rom
            self._status.downloading_rom_position = i + 1

            is_in_device = self._file_system.is_rom_in_device(rom)

            if self._download_existing_roms or not is_in_device:

                try:
                    platform_dir = self._file_system.get_sd_storage_platform_path(
                        rom.platform_slug
                    )
                    dest_filename = self._sanitize_filename(rom.fs_name)
                    dest_path = os.path.join(platform_dir, dest_filename)
                    url = f"{self.host}/{self._roms_endpoint}/{rom.id}/content/{quote(rom.fs_name)}?hidden_folder=true"

                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    if not self._download_file(url, dest_path, rom):
                        return  # Download was aborted or failed

                    # Handle multi-file (ZIP) ROMs
                    if rom.multi:
                        if not self._extract_zip_file(dest_path):
                            return  # Extraction was aborted or failed

                        os.remove(dest_path)
                        print(f"Extracted {rom.name} at {os.path.dirname(dest_path)}")
                except HTTPError as e:
                    if e.code == 403:
                        self._reset_download_status(valid_host=True)
                        continue
                    elif e.code == 404:
                        self._reset_download_status(
                            valid_host=True, valid_credentials=True
                        )
                        continue
                    else:
                        raise
                except URLError:
                    self._reset_download_status(valid_host=True)
                    continue

            filename = self._sanitize_filename(rom.fs_name).split(".")[0]
            if rom.summary:
                text_path = os.path.join(
                    self._file_system.get_sd_catalogue_platform_path(rom.platform_slug),
                    "text",
                    f"{filename}.txt",
                )
                os.makedirs(os.path.dirname(text_path), exist_ok=True)
                with open(text_path, "w") as f:
                    f.write(rom.summary)
                    f.write("\n\n")

                    if rom.first_release_date:
                        dt = datetime.datetime.fromtimestamp(
                            rom.first_release_date / 1000
                        )
                        formatted_date = dt.strftime("%Y-%m-%d")
                        f.write(f"First release date: {formatted_date}\n")

                    if rom.average_rating:
                        f.write(f"Average rating: {rom.average_rating}\n")

                    if rom.genres:
                        f.write(f"Genres: {', '.join(rom.genres)}\n")

                    if rom.franchises:
                        f.write(f"Franchises: {', '.join(rom.franchises)}\n")

                    if rom.companies:
                        f.write(f"Companies: {', '.join(rom.companies)}\n")

            # Don't download covers and previews if the user disabled the option
            if not self._download_assets:
                continue

            box_path = os.path.join(
                self._file_system.get_sd_catalogue_platform_path(rom.platform_slug),
                "box",
                f"{filename}.png",
            )
            preview_path = os.path.join(
                self._file_system.get_sd_catalogue_platform_path(rom.platform_slug),
                "preview",
                f"{filename}.png",
            )

            # Download cover and preview images
            os.makedirs(os.path.dirname(box_path), exist_ok=True)
            os.makedirs(os.path.dirname(preview_path), exist_ok=True)

            self._image_utils.process_assets(
                fullscreen=self._fullscreen_assets,
                cover_url=f"{self.host}{rom.path_cover_small}",
                screenshot_url=f"{self.host}{rom.path_screenshot}",
                box_path=box_path,
                preview_path=preview_path,
                headers=self.headers,
            )

        # End of download
        self._reset_download_status(valid_host=True, valid_credentials=True)
