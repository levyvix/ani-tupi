# Análise do Projeto viu-media/viu
## Melhorias Compatíveis com ani-tupi

**Data**: 2025-12-31
**Análise de**: `/home/levi/viu_media/viu`
**Objetivo**: Documentar padrões e técnicas aplicáveis ao ani-tupi

---

## Visão Geral do Projeto viu-media

**Projeto similar** ao ani-tupi mas mais maduro e escalável:
- **210 arquivos Python** (~14.000 linhas de código)
- **6+ provedores de anime** com arquitetura extensível
- **3 seletores diferentes** (FZF, Rofi, InquirerPy)
- **Sistema de configuração avançado** (Pydantic v2)
- **API abstrata** para múltiplas fontes de dados
- **Gerenciamento de estado** em menu interativo

---

## 1. MELHORIAS - ALTA PRIORIDADE

### 1.1 Sistema de Configuração com Pydantic v2 (IMPACTO: ALTO | ESFORÇO: MÉDIO)

**Status atual do ani-tupi:**
- Configurações espalhadas em `config.py`
- Sem validação em tempo de execução
- Números mágicos em todo o código

**O que o viu-media faz:**
```python
# core/config/model.py
from pydantic import BaseModel, Field

class SearchConfig(BaseModel):
    """Configuration for search behavior."""
    progressive_search_min_words: int = Field(
        default=2, ge=1, le=10,
        description="Minimum words for progressive search"
    )
    fuzzy_threshold: int = Field(
        default=95, ge=0, le=100,
        description="Fuzzy matching threshold"
    )

class CacheConfig(BaseModel):
    """Cache configuration."""
    duration_hours: int = Field(
        default=6, ge=1, le=72,
        description="Cache validity period"
    )
    cache_file: Path = Field(
        default_factory=get_data_path,
        description="Cache storage location"
    )

class AniListConfig(BaseModel):
    """AniList API configuration."""
    api_url: str = "https://graphql.anilist.co"
    client_id: str = Field(default="21576")
    token_file: Path = Field(
        default_factory=lambda: get_data_path() / "anilist_token.json"
    )

class AppConfig(BaseModel):
    """Complete application configuration."""
    search: SearchConfig = Field(default_factory=SearchConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    anilist: AniListConfig = Field(default_factory=AniListConfig)
    # ... mais seções
```

**Benefícios:**
- ✅ Validação em tempo de execução
- ✅ Variáveis de ambiente: `ANI_TUPI__SEARCH__FUZZY_THRESHOLD=85`
- ✅ Arquivo `.env` com valores padrão
- ✅ Suporte a arquivos YAML/JSON
- ✅ Geração automática de help CLI
- ✅ Type hints completos

**Implementação no ani-tupi:**
1. Expandir `config.py` com classes Pydantic aninhadas
2. Adicionar suporte a variáveis de ambiente
3. Validar valores na inicialização
4. Usar `get_data_path()` para caminhos portáveis

**Impacto na base de código:**
- Repository: usar `settings.search.progressive_search_min_words`
- Menu: usar `settings.cache.duration_hours`
- AniList: usar `settings.anilist.api_url`

---

### 1.2 Hierarquia de Exceções Estruturada (IMPACTO: MÉDIO | ESFORÇO: BAIXO)

**Status atual do ani-tupi:**
```python
# Atual - genérico demais
raise Exception("Anime não encontrado")
try:
    # algum código
except Exception as e:
    pass  # Muito amplo
```

**O que o viu-media faz:**
```python
# core/exceptions.py
class ViuError(Exception):
    """Base exception for all viu-media errors."""
    pass

class ProviderError(ViuError):
    """Base for provider-related errors."""
    def __init__(self, provider_name: str, message: str):
        self.provider_name = provider_name
        super().__init__(f"[{provider_name}] {message}")

class NoStreamsFoundError(ProviderError):
    """Raised when no video streams are available."""
    def __init__(self, provider_name: str, anime_title: str, episode: str):
        message = f"No streams found for '{anime_title}' episode {episode}"
        super().__init__(provider_name, message)

class SearchError(ProviderError):
    """Raised when search fails."""
    pass

class EpisodeExtractionError(ProviderError):
    """Raised when episode extraction fails."""
    pass
```

**Aplicação ao ani-tupi:**
```python
# exceptions.py
class AnimeError(Exception):
    """Base exception for ani-tupi errors."""
    pass

class SourceError(AnimeError):
    """Raised when source/plugin operations fail."""
    def __init__(self, source: str, message: str):
        self.source = source
        super().__init__(f"[{source}] {message}")

class SearchError(SourceError):
    """Raised when anime search fails."""
    pass

class NoStreamsError(SourceError):
    """Raised when no video streams found."""
    pass

class AniListError(AnimeError):
    """Raised for AniList API errors."""
    pass

class ConfigError(AnimeError):
    """Raised for configuration errors."""
    pass
```

**Uso no código:**
```python
# Em repository.py
try:
    result = plugin.search_anime(query)
except SourceError as e:
    logger.error(f"Search failed: {e.source} - {e}")
except AnimeError as e:
    logger.error(f"Unexpected error: {e}")

# Tratamento específico em main.py
try:
    # play video
except NoStreamsError:
    show_error("Nenhuma fonte de vídeo encontrada. Tente outro episódio.")
except SourceError:
    show_error("Erro ao buscar fonte de vídeo. Tente outro provedor.")
```

---

### 1.3 Interface Formal para Plugins (ABC) (IMPACTO: MÉDIO | ESFORÇO: BAIXO)

**Status atual do ani-tupi:**
```python
# plugins/animefire.py
class AnimeFirePlugin(PluginInterface):
    name = "animefire"

    @staticmethod
    def search_anime(query: str) -> None:
        # Implementação
        pass
```

**O que o viu-media faz:**
```python
# libs/provider/anime/base.py
from abc import ABC, abstractmethod
from typing import Iterator, Optional
from pydantic import BaseModel

class AnimeMetadata(BaseModel):
    """Anime metadata returned by provider."""
    title: str
    url: str
    poster_url: Optional[str] = None
    description: Optional[str] = None

class Episode(BaseModel):
    """Episode information."""
    number: int
    title: str
    url: str

class BaseAnimeProvider(ABC):
    """Abstract base class for anime providers."""

    HEADERS: ClassVar[Dict[str, str]] = {
        "User-Agent": "Mozilla/5.0..."
    }

    @classmethod
    @abstractmethod
    def search(cls, query: str, limit: int = 10) -> List[AnimeMetadata]:
        """Search for anime by query.

        Args:
            query: Search term
            limit: Maximum results to return

        Returns:
            List of matching anime

        Raises:
            SearchError: If search fails
        """
        pass

    @classmethod
    @abstractmethod
    def get_episodes(cls, url: str) -> List[Episode]:
        """Get episode list for anime.

        Args:
            url: Anime URL from search result

        Returns:
            List of episodes

        Raises:
            EpisodeExtractionError: If extraction fails
        """
        pass

    @classmethod
    @abstractmethod
    def get_streams(cls, episode_url: str) -> Iterator[str]:
        """Get video stream URLs for episode.

        Args:
            episode_url: Episode URL from get_episodes()

        Yields:
            Video stream URLs (m3u8 or mp4)

        Raises:
            NoStreamsError: If no streams found
        """
        pass
```

**Vantagens:**
- ✅ Type hints completos
- ✅ Docstrings estruturadas
- ✅ Erros específicos e claros
- ✅ Pydantic models para dados retornados
- ✅ Testável

**Implementação no ani-tupi:**
```python
# loader.py - refatorar PluginInterface
from abc import ABC, abstractmethod
from typing import List, Iterator, ClassVar, Dict

class PluginInterface(ABC):
    """Abstract base class for anime source plugins."""

    name: ClassVar[str]
    """Plugin identifier (e.g., 'animefire')."""

    languages: ClassVar[List[str]] = ["pt-br"]
    """Supported languages."""

    HEADERS: ClassVar[Dict[str, str]] = {
        "User-Agent": "Mozilla/5.0..."
    }
    """Default HTTP headers."""

    @classmethod
    @abstractmethod
    def search_anime(cls, query: str) -> List[AnimeMetadata]:
        """Search for anime by query."""
        pass

    @classmethod
    @abstractmethod
    def search_episodes(cls, anime_url: str) -> List[Episode]:
        """Get episodes for an anime."""
        pass

    @classmethod
    @abstractmethod
    def search_player_src(cls, episode_url: str) -> Iterator[str]:
        """Get video stream URLs for an episode."""
        pass
```

---

## 2. MELHORIAS - MÉDIA PRIORIDADE

### 2.1 Serviços (Service Layer) (IMPACTO: MÉDIO | ESFORÇO: MÉDIO)

**Conceito:** Encapsular lógica de negócio em serviços reutilizáveis.

**Exemplo do viu-media:**
```python
# cli/service/player/service.py
class PlayerService:
    """Service for video playback management."""

    def __init__(self, config: AppConfig, registry: RegistryService):
        self.config = config
        self.registry = registry
        self._player = create_player(config)

    def play(self, video_url: str, anime_title: str, episode: int):
        """Play video and track history."""
        try:
            self._player.play(video_url)
            self.registry.add_episode(anime_title, episode)
        except Exception as e:
            raise PlayerError(f"Playback failed: {e}")
```

**Serviços recomendados para ani-tupi:**
```python
# services/plugin_service.py
class PluginService:
    """Plugin discovery and management."""

    def load_plugins(self, languages: List[str]) -> Dict[str, PluginInterface]:
        """Load all plugins for given languages."""
        pass

    def search_all(self, query: str) -> SearchResults:
        """Search across all plugins."""
        pass

# services/player_service.py
class PlayerService:
    """Video playback and history tracking."""

    def play_with_history(self, url: str, anime: str, episode: int):
        """Play video and save to history."""
        pass

    def get_continue_watching(self) -> List[AnimeProgress]:
        """Get list of anime to continue."""
        pass

# services/anilist_service.py
class AniListService:
    """AniList API integration."""

    def authenticate(self) -> bool:
        """Authenticate with AniList."""
        pass

    def update_progress(self, anime_id: int, episode: int) -> bool:
        """Update watch progress on AniList."""
        pass

    def get_trending(self, limit: int = 50) -> List[AnimeItem]:
        """Get trending anime."""
        pass
```

**Benefício:**
- ✅ Lógica centralizada
- ✅ Testável
- ✅ Reutilizável entre CLI e TUI
- ✅ Fácil de mockar para testes

---

### 2.2 Lazy Loading de Imports (IMPACTO: BAIXO | ESFORÇO: BAIXO)

**Status atual do ani-tupi:**
```python
# main.py
import selenium  # Importado mesmo se não for usar!
from scrapers import seleniumScraper
```

**O que o viu-media faz:**
```python
# cli/interactive/session.py
class Context:
    """Application context with lazy-loaded services."""

    @property
    def provider(self) -> BaseAnimeProvider:
        """Lazy-load provider on first access."""
        if not self._provider:
            from ...libs.provider.anime.provider import create_provider
            self._provider = create_provider(self.config.general.provider)
        return self._provider

    @property
    def api_client(self) -> BaseApiClient:
        """Lazy-load API client on first access."""
        if not self._api_client:
            from ...libs.media_api.api import create_api_client
            self._api_client = create_api_client(self.config.anilist)
        return self._api_client
```

**Aplicação ao ani-tupi:**
```python
# main.py - ao invés de importar tudo no topo
class AppContext:
    def __init__(self, config):
        self.config = config
        self._repository = None
        self._anilist = None

    @property
    def repository(self):
        if self._repository is None:
            from repository import Repository
            self._repository = Repository(self.config)
        return self._repository

    @property
    def anilist_client(self):
        if self._anilist is None:
            from anilist import AniListClient
            self._anilist = AniListClient(self.config.anilist)
        return self._anilist
```

**Benefício:**
- ✅ Startup mais rápido (não carrega módulos não usados)
- ✅ Melhor experiência para usuários em máquinas lentas
- ✅ Menos memória consumida

---

### 2.3 Logging Estruturado (IMPACTO: MÉDIO | ESFORÇO: MÉDIO)

**Exemplo do viu-media:**
```python
# cli/utils/logging.py
import logging
from logging import LogRecord, Formatter

class ColoredFormatter(Formatter):
    """Custom formatter with colors."""

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }

    def format(self, record: LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = "\033[0m"
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)

# Setup
logger = logging.getLogger("viu-media")
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))
logger.addHandler(handler)
```

**Recomendação para ani-tupi:**
- Adicionar logging estruturado com cores
- Incluir debug mode com mais verbosidade
- Logs de descoberta de plugins
- Logs de busca (query, provider, resultado)

---

## 3. MELHORIAS - BAIXA PRIORIDADE

### 3.1 Fallback para Fuzzy Matching (IMPACTO: BAIXO | ESFORÇO: BAIXO)

**Problema:**
- ani-tupi depende de `fuzzywuzzy` sendo instalada
- Sem a biblioteca, busca fuzzy não funciona

**Solução do viu-media:**
```python
# core/utils/fuzzy.py
try:
    from thefuzz import fuzz as _fuzz_impl
    HAS_THEFUZZ = True
except ImportError:
    HAS_THEFUZZ = False
    _fuzz_impl = None

class PurePythonFuzzy:
    """Pure Python fuzzy matching (fallback)."""

    @staticmethod
    def ratio(s1: str, s2: str) -> int:
        """Simple edit distance based matching."""
        # Implementação sem dependências
        pass

def fuzzy_ratio(s1: str, s2: str) -> int:
    """Get fuzzy match ratio with fallback."""
    if HAS_THEFUZZ:
        return _fuzz_impl.ratio(s1, s2)
    return PurePythonFuzzy.ratio(s1, s2)
```

**Benefício:**
- ✅ Funciona mesmo sem thefuzz instalada (graceful degradation)
- ✅ Qualidade reduzida mas funcional

---

### 3.2 Regex Pattern Manager (IMPACTO: BAIXO | ESFORÇO: BAIXO)

**Problema atual:**
- Padrões regex espalhados em múltiplos arquivos
- Difícil de manter e testar

**Solução do viu-media:**
```python
# core/patterns.py
import re
from dataclasses import dataclass

@dataclass
class Pattern:
    """Pattern wrapper with compilation and caching."""
    pattern: str
    compiled: re.Pattern = None

    def __post_init__(self):
        self.compiled = re.compile(self.pattern, re.IGNORECASE)

    def search(self, text: str):
        return self.compiled.search(text)

    def match(self, text: str):
        return self.compiled.match(text)

# Core patterns
EPISODE_NUMBER = Pattern(r"ep(?:isódio|)?\s*(\d+)", re.IGNORECASE)
RESOLUTION = Pattern(r"(\d{3,4}p)")
QUALITY = Pattern(r"(1080p|720p|480p|SD|HD)")
```

---

### 3.3 Atomic File Writing (IMPACTO: BAIXO | ESFORÇO: MÉDIO)

**Problema:**
- Escrita de arquivo pode corromper cache se processo morrer no meio

**Solução do viu-media:**
```python
# core/utils/file.py
class AtomicWriter:
    """Write file atomically to prevent corruption."""

    def __init__(self, path: Path):
        self.path = path
        self.temp_path = path.with_suffix(path.suffix + ".tmp")

    def __enter__(self):
        self.file = open(self.temp_path, "w")
        return self.file

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.close()
        if exc_type is None:
            self.temp_path.replace(self.path)
        else:
            self.temp_path.unlink()

# Uso
with AtomicWriter(cache_file) as f:
    f.write(json.dumps(data))
# Arquivo só é movido se escrita completou
```

---

## 4. ANTI-PADRÕES A EVITAR

### ❌ Over-Engineering (Complexidade desnecessária)

O viu-media tem **210 arquivos** para um app de terminal. ani-tupi tem ~50 e funciona bem.

**Recomendação:** Não replique tudo blindamente. Pegue apenas o que adiciona valor:
- ✅ Config system (Pydantic) - ÚTIL
- ✅ Exception hierarchy - ÚTIL
- ❌ 15 tipos diferentes de selectors - OVERKILL para ani-tupi
- ❌ Múltiplos players (MPV, VLC) - não necessário
- ✅ ABC interfaces - ÚTIL para plugins

### ❌ Dependency Hell

O viu-media tem muitas dependências opcionais. Manter ani-tupi leve:

```python
# pyproject.toml - bom
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.28",
]

# pyproject.toml - não fazer
[project.optional-dependencies]
advanced = ["yt-dlp", "libtorrent", "dbus-python"]
```

---

## 5. ROADMAP RECOMENDADO

### Fase 1: Configuração (SEMANA 1-2)
**Prioridade:** ALTA | **Esforço:** MÉDIO

- [ ] Expandir `config.py` com Pydantic sections
- [ ] Adicionar suporte a `.env`
- [ ] Adicionar variáveis de ambiente `ANI_TUPI__*`
- [ ] Validação de valores na inicialização

**Benefício:** Centraliza configuração, facilita testes

**Referência:** `@/openspec/changes/add-pydantic-validation/`

---

### Fase 2: Exceções (SEMANA 2-3)
**Prioridade:** MÉDIA | **Esforço:** BAIXO

- [ ] Criar `exceptions.py` com hierarquia
- [ ] Refatorar repository.py para usar exceções
- [ ] Refatorar plugins para lançar exceções específicas
- [ ] Adicionar tratamento em main.py

**Benefício:** Melhor debugging, tratamento específico de erros

---

### Fase 3: Serviços (SEMANA 3-4)
**Prioridade:** MÉDIA | **Esforço:** ALTO

- [ ] Extrair `PluginService`
- [ ] Extrair `PlayerService`
- [ ] Extrair `AniListService`
- [ ] Refatorar main.py para usar serviços

**Benefício:** Código mais testável e reutilizável

---

### Fase 4: Interface de Plugins (SEMANA 4-5)
**Prioridade:** MÉDIA | **Esforço:** BAIXO

- [ ] Refatorar `PluginInterface` com ABC
- [ ] Adicionar type hints completos
- [ ] Adicionar Pydantic models para dados retornados
- [ ] Adicionar docstrings estruturadas

**Benefício:** Plugins mais seguros e documentados

---

## 6. COMPARAÇÃO LADO A LADO

| Aspecto | ani-tupi Atual | viu-media | Recomendação ani-tupi |
|---------|---|---|---|
| **Configuração** | Magic numbers | Pydantic v2 + env vars | Adoptar Pydantic |
| **Exceções** | Genéricas | Hierarquia clara | Implementar hierarquia |
| **Plugin Interface** | Duck typing | ABC formal | Usar ABC |
| **Type Hints** | Parciais | Completos | Expandir coverage |
| **Serviços** | Mínimos | Bem estruturados | Adicionar 3 serviços |
| **Logging** | Básico | Estruturado com cores | Melhorar logging |
| **Testabilidade** | Moderada | Alta | Melhorar com serviços |
| **Linhas de código** | ~3.000 | ~14.000 | Manter < 5.000 |

---

## 7. PADRÕES ESPECÍFICOS PARA REPLICAR

### Pattern 1: Factory Method para Plugins
```python
# loader.py
PLUGIN_REGISTRY: Dict[str, Type[PluginInterface]] = {}

def create_plugin(name: str) -> PluginInterface:
    """Factory method with registry pattern."""
    if name not in PLUGIN_REGISTRY:
        raise ValueError(f"Plugin '{name}' not found")
    return PLUGIN_REGISTRY[name]

def register_plugin(plugin_class: Type[PluginInterface]):
    """Register plugin in factory."""
    PLUGIN_REGISTRY[plugin_class.name] = plugin_class
```

### Pattern 2: Configuração com Defaults
```python
# config.py - Pydantic way
from pydantic import BaseModel, Field

class GeneralConfig(BaseModel):
    provider: str = Field(
        default="animefire",
        description="Default anime provider"
    )
    cache_enabled: bool = Field(
        default=True,
        description="Enable response caching"
    )

    class Config:
        # Permite atribuição de campo
        validate_assignment = True
```

### Pattern 3: Context Manager para Resources
```python
# Já usado em loading.py, expandir:
class Timer:
    """Context manager for timing operations."""
    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed = time.time() - self.start
        logger.debug(f"Operation took {self.elapsed:.2f}s")

# Uso
with Timer() as t:
    result = repository.search_anime(query)
```

---

## 8. EXEMPLOS DE IMPLEMENTAÇÃO

### Exemplo 1: Refatorar repository.py para usar Pydantic

**Antes:**
```python
def search_anime(self, query: str) -> dict:
    # Retorna dict genérico
    return {"title": "...", "url": "...", "source": "..."}
```

**Depois:**
```python
from models import AnimeMetadata
from typing import List

def search_anime(self, query: str) -> List[AnimeMetadata]:
    # Retorna Pydantic models (validados)
    results = []
    for plugin in self.sources.values():
        try:
            anime = plugin.search_anime(query)
            results.append(AnimeMetadata(
                title=anime.title,
                url=anime.url,
                source=plugin.name
            ))
        except SourceError as e:
            logger.warning(f"Search failed in {plugin.name}: {e}")
    return results
```

### Exemplo 2: Adicionar Serviço de Player

**Novo arquivo: services/player_service.py**
```python
from pathlib import Path
from datetime import datetime
from config import settings
from exceptions import PlayerError
from models import PlaybackData

class PlayerService:
    """Service for video playback management."""

    def __init__(self):
        self.history_file = get_data_path() / "history.json"

    def play_episode(
        self,
        video_url: str,
        anime_title: str,
        episode_number: int
    ) -> bool:
        """Play episode and record in history."""
        try:
            # Play via subprocess
            import subprocess
            subprocess.run([
                "mpv",
                video_url,
                "--fullscreen",
                "--cursor-autohide-fs-only"
            ])

            # Record in history
            self.record_watched(anime_title, episode_number)
            return True

        except Exception as e:
            raise PlayerError(f"Playback failed: {e}")

    def record_watched(self, anime_title: str, episode: int):
        """Record watched episode in history."""
        history = self._load_history()
        history[anime_title] = [datetime.now().timestamp(), episode]
        self._save_history(history)

    def _load_history(self) -> dict:
        if self.history_file.exists():
            return json.loads(self.history_file.read_text())
        return {}

    def _save_history(self, history: dict):
        with AtomicWriter(self.history_file) as f:
            f.write(json.dumps(history, indent=2))
```

---

## 9. CHECKLIST PARA IMPLEMENTAÇÃO

- [ ] **Fase 1: Config**
  - [ ] Renomear config model para `AppConfig`
  - [ ] Adicionar `SearchConfig`, `CacheConfig`, `AniListConfig`
  - [ ] Carregar de `.env`
  - [ ] Suporte a env vars `ANI_TUPI__*`

- [ ] **Fase 2: Exceções**
  - [ ] Criar `exceptions.py` com hierarquia
  - [ ] `AnimeError` base
  - [ ] `SourceError` para plugins
  - [ ] `NoStreamsError` para vídeo
  - [ ] Refatorar uso em repository.py

- [ ] **Fase 3: Serviços**
  - [ ] `PlayerService` (play + history)
  - [ ] `PluginService` (load + search)
  - [ ] `AniListService` (API calls)
  - [ ] Refatorar main.py para usar

- [ ] **Fase 4: Plugins**
  - [ ] Converter `PluginInterface` para ABC
  - [ ] Adicionar type hints
  - [ ] Adicionar docstrings

---

## 10. LEITURA RECOMENDADA (Arquivos viu-media)

| Arquivo | Lição |
|---------|-------|
| `core/config/model.py` | Configuração com Pydantic |
| `core/exceptions.py` | Hierarquia de exceções |
| `libs/provider/anime/base.py` | Design de interface |
| `cli/service/registry/service.py` | Service pattern |
| `cli/interactive/session.py` | Lazy loading |
| `core/utils/fuzzy.py` | Fallback patterns |

---

## Conclusão

O projeto viu-media demonstra **padrões de produção** que tornariam ani-tupi mais:
- 🔒 **Robusto** (melhor error handling)
- 🚀 **Performante** (lazy loading)
- 🧪 **Testável** (services + ABC)
- 📦 **Mantível** (hierarquia clara)

**Recomendação principal:** Implementar **Fase 1 (Config)** primeiro, pois é de alto impacto e baixo risco. As outras fases podem ser feitas incrementalmente.

**Estimativa total:** ~80-100 horas distribuídas em 4-6 semanas com commits progressivos.

