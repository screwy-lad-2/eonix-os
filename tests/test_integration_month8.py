import os, pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_build_base_script_exists():
    assert os.path.exists(os.path.join(REPO, "iso/build_base.sh"))

def test_chroot_setup_script_exists():
    assert os.path.exists(os.path.join(REPO, "iso/chroot_setup.sh"))

def test_squashfs_build_script_exists():
    assert os.path.exists(os.path.join(REPO, "iso/build_squashfs.sh"))

def test_iso_build_script_exists():
    assert os.path.exists(os.path.join(REPO, "iso/build_iso.sh"))

def test_grub_config_exists():
    assert os.path.exists(os.path.join(REPO, "iso/grub.cfg")) or \
           os.path.exists(os.path.join(REPO, "iso/grub/grub.cfg"))

def test_iso_test_file_exists():
    assert os.path.exists(os.path.join(REPO, "iso/test_iso_build.py"))
