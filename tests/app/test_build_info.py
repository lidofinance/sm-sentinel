import json

from sentinel.app.build_info import DEFAULT_BUILD_INFO, load_build_info


def test_load_build_info(tmp_path):
    path = tmp_path / "build-info.json"
    path.write_text(json.dumps({"version": "v1.2.3", "branch": "main", "commit": "abc123"}))

    assert load_build_info(path) == {
        "version": "v1.2.3",
        "branch": "main",
        "commit": "abc123",
    }


def test_load_build_info_falls_back_when_file_is_missing(tmp_path):
    assert load_build_info(tmp_path / "missing.json") == DEFAULT_BUILD_INFO
