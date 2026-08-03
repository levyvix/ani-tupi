from utils.persistence import JSONStore


def test_clear_anilist_mapping_removes_saved_entry(temp_dir, monkeypatch):
    from services.anime.anime_persistence import clear_anilist_mapping

    state_dir = temp_dir / "state"
    monkeypatch.setattr("models.config.get_data_path", lambda: state_dir)

    mapping_file = state_dir / "anilist_mappings.json"
    JSONStore(mapping_file).save({"123": {"scraper_title": "Dorohedoro"}})

    clear_anilist_mapping(123)

    assert JSONStore(mapping_file).load({}) == {}


def test_clear_cache_all_also_clears_anilist_mappings(temp_dir, monkeypatch):
    from utils import cache

    state_dir = temp_dir / "state"
    monkeypatch.setattr("models.config.get_data_path", lambda: state_dir)
    monkeypatch.setattr(cache, "clear_cache_all", lambda: None)

    mapping_file = state_dir / "anilist_mappings.json"
    JSONStore(mapping_file).save({"123": {"scraper_title": "Dorohedoro"}})

    cache.clear_cache_all_with_mappings()

    assert JSONStore(mapping_file).load({}) == {}
