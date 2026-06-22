from enum import Enum


class RebuildMode(str, Enum):
    FULL_IMPORT_REBUILD = "FULL_IMPORT_REBUILD"
    RAW_IMPORT_REBUILD = "RAW_IMPORT_REBUILD"
    FULL_REBUILD_FROM_RAW = "FULL_REBUILD_FROM_RAW"
    CORRECTION_REBUILD = "CORRECTION_REBUILD"
    OVERRIDE_REBUILD = "OVERRIDE_REBUILD"
    EXPORT_REBUILD = "EXPORT_REBUILD"

    @property
    def is_implemented(self) -> bool:
        return self in {
            RebuildMode.FULL_IMPORT_REBUILD,
            RebuildMode.RAW_IMPORT_REBUILD,
            RebuildMode.FULL_REBUILD_FROM_RAW,
            RebuildMode.CORRECTION_REBUILD,
            RebuildMode.OVERRIDE_REBUILD,
            RebuildMode.EXPORT_REBUILD,
        }
