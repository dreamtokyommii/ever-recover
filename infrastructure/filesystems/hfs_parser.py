"""HFS+ file system parser.

HONEST STATUS: metadata-based parsing for HFS+ is not implemented in
this build. A previous version of this file silently reported a
successful initialization and then returned zero files for every scan -
a false success that made an unsupported filesystem look like an empty
one. That was misleading and has been removed.

initialize() now raises FileSystemCorruptedError with a clear message.
The calling code (see dashboard_main.py::_create_parser) already handles
parser-initialization failures by falling back to signature-based file
carving (which does not depend on filesystem metadata and works
regardless of HFS+ support), or by surfacing a clear error to the
user if carving is not enabled for the current scan.
"""

from core.interfaces.filesystem_parser import (
    FileSystemParser, FileSystemInfo, FileSystemType, DirectoryEntry,
    FileSystemParserError,
)
from core.models.file_entry import FileEntry
from typing import Iterator, List, Dict, Any, Optional


class HFSPlusParser(FileSystemParser):
    def __init__(self, disk_reader, partition_offset: int = 0):
        super().__init__(disk_reader, partition_offset)

    def initialize(self) -> bool:
        raise FileSystemParserError(
            "HFS+ metadata parsing is not implemented in this build. "
            "Filesystem-aware scanning is unavailable for this volume; "
            "use signature-based carving instead."
        )

    def get_filesystem_info(self) -> FileSystemInfo:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def parse_metadata(self) -> None:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def enumerate_files(self) -> Iterator[FileEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")
        yield  # pragma: no cover - unreachable, keeps this a generator

    def enumerate_directories(self) -> Iterator[DirectoryEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")
        yield  # pragma: no cover

    def get_file_entry(self, reference: int) -> Optional[FileEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def get_file_data(self, file_entry: FileEntry) -> bytes:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def get_file_fragments(self, file_entry: FileEntry) -> List[tuple]:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def get_deleted_files(self) -> Iterator[FileEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")
        yield  # pragma: no cover

    def get_deleted_directories(self) -> Iterator[DirectoryEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")
        yield  # pragma: no cover

    def build_directory_tree(self) -> Dict[str, DirectoryEntry]:
        raise FileSystemParserError("HFS+ parser was not initialized")

    def get_timeline_entries(self) -> Iterator[Dict[str, Any]]:
        raise FileSystemParserError("HFS+ parser was not initialized")
        yield  # pragma: no cover

    def verify_integrity(self) -> bool:
        return False

    @property
    def fs_type(self):
        return FileSystemType.HFS_PLUS
