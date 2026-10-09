import json

from mdconverter.settings import AppSettings


def test_round_trip_with_locked_destination(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(destination="D:/Out", lock_destination=True, llm_model="m").save(path)
    loaded = AppSettings.load(path)
    assert loaded.destination == "D:/Out"
    assert loaded.llm_model == "m"


def test_unlocked_destination_is_not_remembered(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(destination="D:/Out", lock_destination=False).save(path)
    assert AppSettings.load(path).destination == ""


def test_bad_or_unknown_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_enabled": "yes", "unknown": 1, "appearance_mode": "Dark"}), encoding="utf-8")
    loaded = AppSettings.load(path)
    assert loaded.llm_enabled is False
    assert loaded.appearance_mode == "Dark"


def test_corrupt_file_uses_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert AppSettings.load(path) == AppSettings()
