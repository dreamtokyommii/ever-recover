from core.services.privilege_manager import requires_admin_for_source


def test_requires_admin_for_physical_drive_path():
    assert requires_admin_for_source(r"\\.\PhysicalDrive1") is True
    assert requires_admin_for_source("E:\\") is True


def test_does_not_require_admin_for_file_and_folder_paths():
    assert requires_admin_for_source(r"C:\Users\Public\file.txt") is False
    assert requires_admin_for_source(r"C:\Users\Public") is False
