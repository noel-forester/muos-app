from collections import namedtuple

Rom = namedtuple(
    "Rom",
    [
        "id",
        "name",
        "fs_name",
        "platform_slug",
        "fs_extension",
        "fs_size",
        "fs_size_bytes",
        "multi",
        "languages",
        "regions",
        "revision",
        "tags",
    ],
)
Collection = namedtuple("Collection", ["id", "name", "rom_count", "virtual"])
Platform = namedtuple("Platform", ["id", "display_name", "slug", "rom_count"])
SaveData = namedtuple("SaveData", [
    "id", 
    "rom_id", 
    "user_id", 
    "file_name", 
    "file_name_no_tags", 
    "file_name_no_ext", 
    "file_extension", 
    "file_path", 
    "file_size_bytes", 
    "full_path", 
    "download_path", 
    "missing_from_fs", 
    "created_at", 
    "updated_at", 
    "emulator", 
    "screenshot"
])

StateSave = namedtuple("StateSave", [
    "id", 
    "rom_id", 
    "user_id", 
    "file_name", 
    "file_name_no_tags", 
    "file_name_no_ext", 
    "file_extension", 
    "file_path", 
    "file_size_bytes", 
    "full_path", 
    "download_path", 
    "missing_from_fs", 
    "created_at", 
    "updated_at", 
    "emulator", 
    "screenshot"
])
