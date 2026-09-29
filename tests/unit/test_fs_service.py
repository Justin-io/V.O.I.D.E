"""Unit Tests for FilesystemService."""

import os
import tempfile
import pytest
from voide.native.linux_host.fs_service import FilesystemService, SecurityError


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_path_traversal_rejection(workspace):
    fs = FilesystemService(workspace)
    with pytest.raises(SecurityError):
        fs.read_file("../../../etc/passwd")

    with pytest.raises(SecurityError):
        fs.write_file("../malicious.sh", "echo bad")


def test_atomic_write_and_read(workspace):
    fs = FilesystemService(workspace)
    res = fs.write_file("src/main.py", "print('hello world')\n")
    assert res["path"] == "src/main.py"
    assert res["changed"] is True
    assert len(res["content_hash"]) == 64

    read_res = fs.read_file("src/main.py")
    assert "print('hello world')" in read_res["content"]
    assert read_res["content_hash"] == res["content_hash"]
    assert read_res["lines"] == 2


def test_list_directory_and_search(workspace):
    fs = FilesystemService(workspace)
    fs.write_file("file1.txt", "alpha beta")
    fs.write_file("sub/file2.txt", "gamma delta beta")

    entries = fs.list_directory("")
    names = [e["name"] for e in entries]
    assert "file1.txt" in names
    assert "sub" in names

    matches = fs.search_files("beta")
    assert len(matches) == 2
    paths = [m["path"] for m in matches]
    assert "file1.txt" in paths
    assert "sub/file2.txt" in paths


def test_apply_patch(workspace):
    fs = FilesystemService(workspace)
    fs.write_file("code.py", "def add(a, b):\n    return a - b\n")

    patch = (
        "--- code.py\n"
        "+++ code.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )

    patch_res = fs.apply_patch("code.py", patch)
    assert patch_res["diff_applied"] is True

    read_res = fs.read_file("code.py")
    assert "return a + b" in read_res["content"]


def test_create_delete_rename(workspace):
    fs = FilesystemService(workspace)
    # Create directory
    dir_res = fs.create_directory("new_folder/sub")
    assert dir_res["created"] is True
    assert os.path.isdir(os.path.join(workspace, "new_folder/sub"))

    # Write file
    fs.write_file("new_folder/sub/sample.txt", "hello")
    assert os.path.isfile(os.path.join(workspace, "new_folder/sub/sample.txt"))

    # Rename file
    ren_res = fs.rename_file("new_folder/sub/sample.txt", "new_folder/sub/renamed.txt")
    assert ren_res["renamed"] is True
    assert not os.path.exists(os.path.join(workspace, "new_folder/sub/sample.txt"))
    assert os.path.exists(os.path.join(workspace, "new_folder/sub/renamed.txt"))

    # Delete file
    del_res = fs.delete_file("new_folder/sub/renamed.txt")
    assert del_res["deleted"] is True
    assert not os.path.exists(os.path.join(workspace, "new_folder/sub/renamed.txt"))

    # Delete folder
    del_dir_res = fs.delete_file("new_folder")
    assert del_dir_res["deleted"] is True
    assert not os.path.exists(os.path.join(workspace, "new_folder"))

