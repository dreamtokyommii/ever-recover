from datetime import datetime

from core.models.device import DeviceInfo, DeviceType, FileSystemType
from core.models.scan_result import ScanResult


def test_scan_result_exposes_duration_seconds_for_demo_compatibility():
    device = DeviceInfo(
        device_id="demo-device",
        path="/tmp/demo.img",
        label="demo",
        device_type=DeviceType.VIRTUAL,
        file_system=FileSystemType.NTFS,
        total_size=1024,
        free_space=512,
        is_removable=False,
    )
    start_time = datetime(2026, 7, 10, 20, 30, 0)

    scan_result = ScanResult(scan_id="demo-scan", device=device, start_time=start_time)
    scan_result.end_time = start_time

    assert scan_result.duration_seconds == 0.0
