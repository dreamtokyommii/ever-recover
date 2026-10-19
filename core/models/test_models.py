# test_models.py
try:
    # when run as part of the package
    from .models import DeviceInfo, DeviceType, FileSystemType
except Exception:
    # fallback when running the file directly (e.g. via VSCode)
    from ever_recover.core.models import DeviceInfo, DeviceType, FileSystemType

# Create a test device
device = DeviceInfo(
    device_id="test-001",
    path="\\\\.\\PhysicalDrive1",
    label="RECOVERY_DRIVE",
    device_type=DeviceType.USB_DRIVE,
    file_system=FileSystemType.NTFS,
    total_size=32_000_000_000,
    free_space=10_000_000_000,
    is_removable=True,
)

print(f"Device: {device.label}")
print(f"Size: {device.display_size}")
print(f"Used: {device.usage_percentage:.1f}%")
print(f"TRIM Warning: {device.has_trim_warning}")