# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto segue [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ✨ **Trocar Fonte após Episódio**: Nova opção "🔄 Trocar fonte" no menu pós-episódio
  - Permite alternar entre versões dublada/legendada/diferentes scrapers após assistir um episódio
  - Útil quando a fonte atual não tem episódios mais recentes disponíveis
  - Mostra todas as variações encontradas para o anime base
  - Exemplo: Assistindo "Horimiya (Dublado)" → sem ep 10 dublado → clica "🔄 Trocar fonte" → seleciona "Horimiya (Legendado)" → continua do ep 10
  - Implementado em ambos fluxos: busca normal e AniList
  - Commits: `8cf4295`, `b6642f5`, `12e5e57`

## [0.1.0] - 2025-12-31

### Added

- Initial release
- 🎬 Anime streaming CLI com suporte a múltiplos scrapers (animefire, animesonlinecc)
- 📺 Integração com AniList.co (buscar, sincronizar progresso)
- 📚 Leitor de Mangá do MangaDex
- 💾 Histórico local de leitura/assistência
- ⚙️ Configuração centralizada com Pydantic
- 🎨 TUI com Rich + InquirerPy (menus e spinners)
- 🔌 Sistema de plugins para scrapers

[Unreleased]: https://github.com/levyvix/ani-tupi/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/levyvix/ani-tupi/releases/tag/v0.1.0
