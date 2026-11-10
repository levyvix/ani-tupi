"""Application configuration using Pydantic v2 and a local JSON settings file."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


def get_data_path() -> Path:
    """Get OS-specific data directory for ani-tupi.

    Returns:
        Path: user-local application data directory for the current platform
    """
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "ani-tupi"
    return Path.home() / ".local" / "state" / "ani-tupi"


def get_user_config_path() -> Path:
    """Get OS-specific user configuration directory for ani-tupi."""
    if os.name == "nt":
        return Path.home() / "AppData" / "Roaming" / "ani-tupi"
    return Path.home() / ".config" / "ani-tupi"


def get_user_settings_file() -> Path:
    """Get file path for persisted user settings overrides."""
    return get_user_config_path() / "settings.json"


def load_user_settings_overrides() -> dict:
    """Load user settings overrides from JSON file."""
    settings_file = get_user_settings_file()
    if not settings_file.exists():
        return {}
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_user_settings_overrides(overrides: dict) -> None:
    """Persist user settings overrides atomically."""
    settings_file = get_user_settings_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = settings_file.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    temp_file.replace(settings_file)


class AniListSettings(BaseModel):
    """AniList API configuration."""

    api_url: str = Field(
        "https://graphql.anilist.co",
        description="Endereço da API GraphQL do AniList",
        json_schema_extra={"editable": False},
    )
    auth_url: str = Field(
        "https://anilist.co/api/v2/oauth/authorize",
        description="Endereço de autorização OAuth",
        json_schema_extra={"editable": False},
    )
    client_id: int = Field(
        38122,
        gt=0,
        description="ID público do cliente OAuth",
        json_schema_extra={"editable": False},
    )
    token_file: Path = Field(
        default_factory=lambda: get_data_path() / "anilist_token.json",
        description="Caminho do arquivo que armazena o token de acesso",
    )
    prefer_english_title: bool = Field(
        False,
        description="Usar o título em inglês nas buscas (sim) ou em romaji (não)",
    )
    manga_prefer_english_title: bool = Field(
        False,
        description="Usar o título em inglês nas buscas de mangá (sim) ou em romaji (não)",
    )
    manga_auto_sync: bool = Field(
        True,
        description="Sincronizar automaticamente o progresso do mangá com o AniList após a confirmação",
    )
    manga_progress_confirmation: bool = Field(
        True,
        description="Pedir confirmação ao terminar de ler um capítulo",
    )
    request_timeout_seconds: float = Field(
        30.0,
        gt=0,
        le=120,
        description="Tempo limite, em segundos, das solicitações à API do AniList",
    )


class CacheSettings(BaseModel):
    """Unified cache configuration with TTL and refresh options."""

    cache_dir: Path = Field(
        default_factory=lambda: get_data_path() / "cache",
        description="Caminho da pasta de cache",
    )
    anilist_auto_discover: bool = Field(
        True,
        description="Encontrar automaticamente o ID do AniList em buscas manuais por similaridade",
    )
    anilist_fuzzy_threshold: int = Field(
        90,
        ge=70,
        le=100,
        description="Pontuação mínima de similaridade (0 a 100) para encontrar o ID do AniList",
    )
    episodes_cache_enabled: bool = Field(
        False,
        description="Guardar listas de episódios em cache (desativado por padrão para buscar episódios novos)",
    )
    # TTL Configuration
    search_cache_ttl_seconds: int = Field(
        3600,
        ge=60,
        description="Tempo de validade do cache de buscas, em segundos (padrão: 1 hora)",
    )
    episodes_cache_ttl_seconds: int = Field(
        1800,
        ge=60,
        description="Tempo de validade do cache de episódios, em segundos (padrão: 30 minutos)",
    )
    video_url_cache_ttl_seconds: int = Field(
        7200,
        ge=60,
        description="Tempo de validade do cache de links de vídeo, em segundos (padrão: 2 horas)",
    )
    cache_max_size_bytes: int = Field(
        50 * 1024 * 1024,  # 50 MB
        ge=1_000_000,
        description="Tamanho máximo do cache em bytes antes de remover os itens menos usados (padrão: 50 MB)",
    )
    # Background refresh configuration
    background_refresh_enabled: bool = Field(
        False,
        description="Atualizar em segundo plano itens vencidos do cache (desativado por padrão)",
    )
    background_refresh_threshold_seconds: int = Field(
        2700,  # 45 minutes
        ge=60,
        description="Idade mínima, em segundos, para atualizar itens do cache em segundo plano",
    )
    background_refresh_max_workers: int = Field(
        2,
        ge=1,
        le=16,
        description="Número máximo de tarefas paralelas para atualizar o cache",
    )


class SearchSettings(BaseModel):
    """Anime search configuration."""

    progressive_search_min_words: int = Field(
        1,  # Changed from 2 to support single-word anime like "Dandadan"
        ge=1,
        description="Número mínimo de palavras usadas na busca progressiva",
    )
    incremental_max_results: int = Field(
        20,
        ge=1,
        description="Quantidade de resultados que interrompe a ampliação gradual dos termos da busca",
    )
    top_results_limit: int = Field(
        10,
        ge=5,
        le=50,
        description="Número máximo de resultados exibidos inicialmente, antes de mostrar todos",
    )
    preferred_audio: str = Field(
        "dublado",
        pattern="^(dublado|legendado)$",
        description="Áudio preferido no AnimesDigital: dublado ou legendado",
    )
    enable_title_resolution: bool = Field(
        True,
        description="Tentar novamente buscas manuais usando títulos encontrados externamente quando a busca direta falhar",
    )
    title_resolution_timeout_seconds: float = Field(
        8.0,
        gt=0,
        le=30,
        description="Tempo limite de consulta a cada serviço externo de busca de títulos",
    )
    title_resolution_cache_ttl_seconds: int = Field(
        7 * 24 * 3600,
        ge=60,
        description="Validade do cache de títulos de anime encontrados, em segundos",
    )
    title_resolution_min_confidence: int = Field(
        75,
        ge=0,
        le=100,
        description="Confiança mínima para tentar novamente a busca com um título encontrado externamente",
    )


class PluginSettings(BaseModel):
    """Plugin/scraper management settings."""

    disabled_plugins: list[str] = Field(
        default_factory=list,
        description="Lista de fontes desativadas (por exemplo: ['sushianimes'])",
    )
    priority_order: list[str] = Field(
        default_factory=lambda: [
            "dattebayo",
            "anitube",
            "otakulogia",
            "sushianimes",
            "animesdigital",
            "animefire",
            "animesonlineio",
            "goyabu",
            "anroll",
            "animesonlinecc",
        ],
        description="Ordem de preferência das fontes (a primeira tem maior prioridade)",
    )

    @field_validator("priority_order")
    @classmethod
    def append_missing_plugins(cls, v: list[str]) -> list[str]:
        """Append any installed plugins not yet in the saved priority list."""
        plugins_dir = Path(__file__).parent.parent / "scrapers" / "plugins"
        skip = {"__init__.py", "utils.py"}
        installed = {f.stem for f in plugins_dir.glob("*.py") if f.name not in skip}
        missing = [p for p in installed if p not in v]
        return v + sorted(missing)


class PerformanceSettings(BaseModel):
    """Performance optimization settings for scrapers."""

    # HTTP Client Settings
    http_timeout: int = Field(
        15,
        ge=5,
        le=60,
        description="Tempo limite padrão das solicitações HTTP, em segundos",
    )
    http_pool_connections: int = Field(
        10,
        ge=5,
        le=50,
        description="Número de conjuntos de conexões mantidos em cache",
    )
    http_pool_maxsize: int = Field(
        20,
        ge=10,
        le=100,
        description="Número máximo de conexões por conjunto",
    )
    http_retry_attempts: int = Field(
        3,
        ge=1,
        le=5,
        description="Número de tentativas para solicitações HTTP que falharem",
    )

    # Cache Settings (additional to existing cache settings)
    search_cache_ttl: int = Field(
        300,
        ge=60,
        le=1800,
        description="Validade do cache de resultados de busca, em segundos (padrão: 5 minutos)",
    )
    episodes_cache_ttl: int = Field(
        1800,
        ge=300,
        le=3600,
        description="Validade do cache de listas de episódios, em segundos (padrão: 30 minutos)",
    )
    video_url_cache_ttl_seconds: int = Field(
        3600,
        ge=300,
        le=86400,
        description="Validade do cache de links de vídeo, em segundos (padrão: 1 hora)",
    )
    smart_cache_max_size_mb: int = Field(
        100,
        ge=50,
        le=500,
        description="Tamanho máximo do cache inteligente, em MB",
    )

    # Unified Cache Settings
    cache_type: str = Field(
        "disk",
        description="Tipo de cache: memória, disco ou híbrido",
    )

    # Consolidated Cache TTL Settings (replaces duplicate duration_hours fields)
    default_ttl_hours: int = Field(
        168,
        ge=1,
        le=720,
        description="Validade padrão do cache, em horas (7 dias; máximo de 30 dias)",
    )
    source_ttls: dict[str, int] = Field(
        default_factory=lambda: {
            "search": 5,  # 5 minutes for search results
            "episodes": 30,  # 30 minutes for episode lists
            "video": 15,  # 15 minutes for video URLs (expire quickly)
            "manga": 24,  # 24 hours for manga chapters
            "anilist_meta": 720,  # 30 days for AniList metadata
        },
        description="Validade do cache em horas para cada tipo de dado",
    )


class AnimeDownloadSettings(BaseModel):
    """Anime download and local library settings."""

    download_directory: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "share" / "ani-tupi" / "anime",
        description="Pasta onde os episódios de anime baixados serão salvos",
    )
    max_parallel_downloads: int = Field(
        3,
        ge=1,
        le=16,
        description="Número máximo de episódios baixados ao mesmo tempo (1 = um por vez; 16 = máximo)",
    )
    video_format: str = Field(
        "mkv",
        description="Formato padrão dos vídeos baixados (mkv, mp4 etc.)",
    )
    skip_already_downloaded: bool = Field(
        True,
        description="Ignorar episódios já baixados em operações em lote",
    )


class OfflineSyncConfig(BaseModel):
    """Configuration for offline AniList sync queue."""

    max_retry_count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Número máximo de tentativas antes de desistir de uma sincronização",
    )
    enable_auto_retry: bool = Field(
        default=True,
        description="Tentar novamente sincronizações pendentes ao iniciar o aplicativo",
    )
    enable_file_cleanup: bool = Field(
        default=True,
        description="Excluir arquivos locais dos episódios após uma sincronização bem-sucedida",
    )
    delete_after_watch: bool = Field(
        default=True,
        description="Excluir arquivos locais após assistir, mesmo sem sincronizar com o AniList",
    )


class MangaSettings(BaseModel):
    """Manga reader settings with multi-source support."""

    api_url: str = Field(
        "https://api.mangadex.org",
        description="Endereço base da API do MangaDex",
        json_schema_extra={"editable": False},
    )

    output_directory: Path = Field(
        default_factory=lambda: Path.home() / ".manga_tupi",
        description="Pasta onde os capítulos de mangá serão salvos",
    )
    preferred_sources: list[str] = Field(
        default_factory=lambda: ["mangalivre", "mugiwaras", "mangadex"],
        description="Fontes de mangá preferidas, em ordem de prioridade",
    )
    pdf_reader: str | None = Field(
        None,
        description="Leitor de PDF (zathura, evince, okular ou mupdf). Vazio = detectar automaticamente",
    )
    pdf_reader_priority: list[str] = Field(
        default_factory=lambda: ["zathura", "evince", "okular", "mupdf", "xdg-open"],
        description="Ordem de preferência para detectar leitores de PDF",
    )
    delete_images_after_pdf: bool = Field(
        True,
        description="Excluir as imagens PNG após criar o PDF e manter apenas o arquivo PDF",
    )
    pdf_quality: int = Field(
        85,
        ge=1,
        le=100,
        description="Qualidade JPEG das imagens no PDF (0 a 100; valores menores geram arquivos menores)",
    )
    auto_create_pdf: bool = Field(
        True,
        description="Criar um PDF automaticamente após baixar as imagens",
    )
    zathura_auto_config: bool = Field(
        True,
        description="Configurar o Zathura automaticamente para ajustar a página à largura da tela",
    )
    # Download for later settings
    default_download_range: int = Field(
        5,
        ge=1,
        le=100,
        description="Número padrão de capítulos para baixar ao escolher a opção de download",
    )
    auto_open_after_download: bool = Field(
        False,
        description="Abrir o leitor de PDF após o download (não = permanecer no menu)",
    )
    skip_already_downloaded: bool = Field(
        True,
        description="Ignorar capítulos já baixados em operações em lote",
    )
    download_storage_dir: str | None = Field(
        None,
        description="Pasta personalizada para os PDFs baixados (vazio = usar a pasta de saída)",
    )
    auto_delete_read_chapters: bool = Field(
        True,
        description="Excluir os arquivos dos capítulos após marcá-los como lidos para liberar espaço",
    )
    debug_download_failures: bool = Field(
        False,
        description="Registrar detalhes quando um download falhar para ajudar a identificar o problema",
    )
    max_parallel_downloads: int = Field(
        0,
        ge=0,
        le=16,
        description="Número máximo de capítulos baixados ao mesmo tempo (0 = usar os núcleos da CPU; 1 = um por vez)",
    )


class AiringSettings(BaseModel):
    """Settings for airing episodes feature."""

    grace_period_days: int = Field(
        60,
        ge=1,
        le=365,
        description="Dias para manter um anime visível na aba Novos episódios após o fim da exibição (padrão: 60)",
    )


class AiringDownloadsSettings(BaseModel):
    """Configuration for the non-interactive airing download monitor."""

    poll_interval_minutes: int = Field(
        30,
        description="Intervalo do monitor em minutos; deve dividir uma hora sem resto",
    )

    @field_validator("poll_interval_minutes")
    @classmethod
    def validate_poll_interval(cls, value: int) -> int:
        """Accept intervals that align with the hourly systemd timer schedule."""
        valid_intervals = {1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}
        if value not in valid_intervals:
            raise ValueError(f"poll_interval_minutes must be one of {sorted(valid_intervals)}")
        return value


# Singular spelling is kept as a compatibility alias for service callers.
AiringDownloadSettings = AiringDownloadsSettings


class UpdateCheckSettings(BaseModel):
    """Configuration for startup update checks."""

    enabled: bool = Field(
        True,
        description="Verificar atualizações automaticamente ao iniciar o aplicativo",
    )
    interval_hours: int = Field(
        24,
        ge=1,
        le=720,
        description="Intervalo mínimo, em horas, entre verificações de atualização bem-sucedidas",
    )
    request_timeout_seconds: float = Field(
        2.0,
        gt=0,
        le=30,
        description="Tempo limite das solicitações HTTP para verificar atualizações",
    )
    release_source_url: str = Field(
        "https://api.github.com/repos/levyvix/ani-tupi/releases/latest",
        description="Endereço oficial usado para consultar a versão mais recente",
        json_schema_extra={"editable": False},
    )
    update_command: str = Field(
        "curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/master/install.sh | bash",
        description="Comando exibido quando houver uma atualização disponível",
        json_schema_extra={"editable": False},
    )


class RuntimeSettings(BaseModel):
    """Runtime diagnostics and player options, persisted in settings.json."""

    debug_incremental_search: bool = Field(
        False, description="Registrar detalhes das buscas progressivas de anime"
    )
    debug_mpv: bool = Field(False, description="Registrar detalhes da reprodução no MPV")
    disable_ipc: bool = Field(False, description="Desativar a integração IPC com o MPV")
    mpv_log_file: str | None = Field(
        None,
        description="Caminho personalizado do arquivo de registros do MPV (vazio = usar o padrão)",
    )


class AppSettings(BaseModel):
    """Root application settings; user overrides are stored in settings.json."""

    anilist: AniListSettings = AniListSettings()  # type: ignore[call-arg]
    cache: CacheSettings = CacheSettings()  # type: ignore[call-arg]
    search: SearchSettings = SearchSettings()  # type: ignore[call-arg]
    plugins: PluginSettings = PluginSettings()  # type: ignore[call-arg]
    anime_download: AnimeDownloadSettings = AnimeDownloadSettings()  # type: ignore[call-arg]
    offline_sync: OfflineSyncConfig = OfflineSyncConfig()  # type: ignore[call-arg]
    manga: MangaSettings = MangaSettings()  # type: ignore[call-arg]
    performance: PerformanceSettings = PerformanceSettings()  # type: ignore[call-arg]
    airing: AiringSettings = AiringSettings()  # type: ignore[call-arg]
    airing_downloads: AiringDownloadsSettings = AiringDownloadsSettings()  # type: ignore[call-arg]
    updates: UpdateCheckSettings = UpdateCheckSettings()  # type: ignore[call-arg]
    runtime: RuntimeSettings = RuntimeSettings()

    @property
    def debug_incremental_search(self) -> bool:
        return self.runtime.debug_incremental_search

    @property
    def debug_mpv(self) -> bool:
        return self.runtime.debug_mpv

    @property
    def disable_ipc(self) -> bool:
        return self.runtime.disable_ipc

    @property
    def mpv_log_file(self) -> str | None:
        value = self.runtime.mpv_log_file
        return value.strip() or None if value else None


# Singleton instance - import and use throughout the app
settings = AppSettings.model_validate(load_user_settings_overrides())
