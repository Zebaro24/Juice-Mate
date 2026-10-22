from pathlib import Path

from juice_mate.folders import migrate


def test_settings_move_out_of_the_install_folder_once(tmp_path: Path) -> None:
    old, new = tmp_path / "Local" / "JuiceMate", tmp_path / "Roaming" / "JuiceMate"
    old.mkdir(parents=True)
    (old / "settings.json").write_text('{"sensors": ["cpu.load"]}')
    migrate(new, old)
    assert (new / "settings.json").read_text() == '{"sensors": ["cpu.load"]}'
    (old / "settings.json").write_text('{"sensors": []}')
    migrate(new, old)  # the new file wins from now on
    assert (new / "settings.json").read_text() == '{"sensors": ["cpu.load"]}'


def test_nothing_to_carry_over_on_a_clean_pc(tmp_path: Path) -> None:
    migrate(tmp_path / "new", tmp_path / "old")
    assert not (tmp_path / "new").exists()
