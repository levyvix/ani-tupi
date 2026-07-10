from utils.persistence import JSONStore


def test_clear_anilist_mapping_removes_saved_entry(temp_dir, monkeypatch):
    from services.anime.mappings import clear_anilist_mapping

    state_dir = temp_dir / "state"
    monkeypatch.setattr("models.config.get_data_path", lambda: state_dir)

    mapping_file = state_dir / "anilist_mappings.json"
    JSONStore(mapping_file).save({"123": {"scraper_title": "Dorohedoro"}})

    clear_anilist_mapping(123)

    assert JSONStore(mapping_file).load({}) == {}
