# ani-tupi justfile - Common development tasks

# Run ani-tupi with query
push:
  git pull --rebase && git push

@query query:
    uv run ani-tupi --query "{{query}}"

# Run ani-tupi anilist menu
@anilist:
    uv run ani-tupi anilist

# Run ani-tupi with continue watching
@continue:
    uv run ani-tupi --continue-watching

# Clear anime search cache (query cache only)
@clear-search-cache:
    rm -rf ~/.local/state/ani-tupi/cache
    echo "✅ Search cache cleared!"

# Clear anime search cache (query cache and episode cache)
@clear-cache:
    uv run ani-tupi --clear-cache
    uv run scripts/clean_caches.py

# Clear entire cache directory (also clears state)
@clear-cache-full:
    rm -rf ~/.cache/ani-tugo
    rm -rf ~/.local/state/ani-tupi/cache
    echo "✅ Full cache directory removed!"

# Clear watch history
@clear-history:
    rm -f ~/.local/state/ani-tupi/history.json
    echo "✅ Watch history cleared!"

# Clear everything (cache + history + mappings)
@clear-all:
    just clear-cache-full
    just clear-history
    rm -f ~/.local/state/ani-tupi/anilist_mappings.json
    echo "✅ AniList mappings cleared!"

# Run tests
@test:
    uv run pytest

# Run linter
@lint:
    uv run ruff check .

# Format code
@format:
    uv run ruff format .

# Run all static quality checks
@check:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run deptry .
    uv run vulture commands manga_scrapers models scrapers services ui utils main.py manga_tupi.py plugin_manager.py --min-confidence 90

# Install as global CLI
@install:
    python3 install-cli.py

# Show help
@help:
    just --list
