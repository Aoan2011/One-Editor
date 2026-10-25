from utils import detect_language, safe_read, build_shell_command


def test_detect_language_python():
    assert detect_language("foo.py") == "python"


def test_detect_language_unknown():
    assert detect_language("foo.xyz") is None


def test_safe_read_missing_file(tmp_path):
    assert safe_read(str(tmp_path / "nope.txt")) is None


def test_safe_read_ok(sample_text_file):
    content = safe_read(str(sample_text_file))
    assert content == "hello\nworld\n"


def test_build_shell_command_with_spaces():
    cmd = ["python", "/path/with space/file.py"]
    result = build_shell_command(cmd)
    assert "'/path/with space/file.py'" in result or "\"/path/with space/file.py\"" in result