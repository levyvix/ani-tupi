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
    from services.anime import anime_persistence
    from services.anime.airing_sources import AiringSourceStore
    from models.download import AiringSourceBinding

    state_dir = temp_dir / "state"
    monkeypatch.setattr("models.config.get_data_path", lambda: state_dir)
    monkeypatch.setattr(cache, "clear_cache_all", lambda: None)

    mapping_file = state_dir / "anilist_mappings.json"
    JSONStore(mapping_file).save({"123": {"scraper_title": "Dorohedoro"}})
    source_store = AiringSourceStore(state_dir / "airing_download_sources.json")
    source_store.save_binding(
        123,
        AiringSourceBinding(
            title="Dorohedoro",
            source="src",
            anime_url="https://source.example/anime",
        ),
    )
    monkeypatch.setattr(anime_persistence, "AiringSourceStore", lambda: source_store)

    cache.clear_cache_all_with_mappings()

    assert JSONStore(mapping_file).load({}) == {}
    assert source_store.effective(123).binding is None
