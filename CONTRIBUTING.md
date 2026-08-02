# Contributing to ani-tupi

Obrigado por contribuir! Antes de mexer no código, leia esta seção sobre a
**filosofia de fontes** — ela é o coração do projeto e guia praticamente todas
as decisões de design. Qualquer mudança precisa preservar os princípios abaixo.

Para regras de estilo, arquitetura em três camadas (commands → services →
plugins), configuração via Pydantic e workflow de release, veja
[`CLAUDE.md`](./CLAUDE.md).

---

## Filosofia de fontes (leia isto primeiro)

### O problema

Nem toda fonte é igual. Ao buscar um anime, cada scraper devolve o mesmo
episódio, mas com qualidades muito diferentes de entrega:

| Dimensão            | Fonte boa (ex.: `anitube`, `animesdigital`) | Fonte ruim (ex.: `animefire`, `animesonlinecc`) |
| ------------------- | ------------------------------------------- | ----------------------------------------------- |
| Velocidade do link  | Link direto, resolve rápido                 | Cadeia de resolução lenta (blogger → googlevideo) |
| Qualidade do vídeo  | HD                                          | Frequentemente SD                               |
| Legenda             | Melhor sincronização e tradução             | Pior ou ausente                                 |

**Decisão do autor:** priorizar as fontes boas sempre que possível. O usuário
prefere assistir num link rápido HD com boa legenda a esperar um stream SD lerdo.

### Por que nem sempre pegamos a melhor

Os sites estão numa corrida armamentista constante contra bots (nós). Quando a
defesa anti-bot de uma fonte boa aperta, ela para de responder e sobra o
"resto": candidatos `blogger` / `googlevideo`, que são lentos e SD. Por isso o
sistema **degrada com elegância** em vez de simplesmente falhar — mas sempre
tentando o melhor primeiro.

Foi por causa dessa corrida que candidatos `blogger` puros foram descartados em
alguns fluxos (ver commit `feat: rank-major source fallback + drop blogger
candidates`): quando só resta blogger, o custo/qualidade muitas vezes não
compensa.

### Como isso vive no código

Três mecanismos implementam essa filosofia. **Não quebre nenhum deles.**

**1. Ordem de prioridade das fontes** — `models/config.py` (`PluginSettings.priority_order`):

```python
priority_order = [
    "dattebayo", "sushianimes", "anitube", "animesdigital",
    "animefire", "goyabu", "animesonlinecc",
]
```

Primeiro = maior prioridade. Fontes melhores ficam no topo. Ordenação aplicada
via `services/repository/episode_repository.py::sort_by_priority`. Configurável por ambiente —
o usuário pode reordenar sem tocar em código.

**2. Fallback rank-major** — `services/anime/playback_service.py`:

Ao reproduzir, tentamos o candidato de **melhor qualidade (rank 0) de TODAS as
fontes** antes de descer para o próximo rank. Ou seja: HD de todas as fontes
primeiro, só depois SD. Isso prioriza qualidade em toda a lista antes de aceitar
um stream pior de qualquer fonte. Extração é lazy e cacheada por fonte.

**3. Visibilidade das fontes por título** — dedup em `services/repository.py`:

O usuário quer **ver quais fontes existem para o título buscado** para escolher o
anime com as melhores fontes (mais velocidade, melhor legenda, melhor
qualidade). A deduplicação por `normalize_title_for_dedup()` funde o mesmo anime
de várias fontes numa entrada só, exibindo a lista de fontes:

```
"Anime A Dublado [anitube, animesdigital, animefire]"
```

Assim dá para preferir uma entrada que tem `anitube`/`animesdigital` em vez de
uma que só tem `animefire`/`animesonlinecc`.

### Regra para qualquer PR

> Toda mudança no código deve manter: (a) fontes boas com prioridade,
> (b) fallback que tenta a melhor qualidade primeiro, (c) visibilidade de quais
> fontes cada título tem.

Se sua alteração afeta scraping, playback ou exibição de resultados, explique no
PR como esses três pontos foram preservados.

---

## Adicionando uma fonte nova

1. Crie `scrapers/plugins/novafonte.py` implementando o protocolo `Scraper`
   (`search`, `get_episodes`). Auto-descoberto por `scrapers/loader.py` — sem
   registro manual.
2. Posicione-a corretamente em `priority_order` conforme a qualidade/velocidade
   real da entrega (fonte boa → topo; fonte que cai em blogger → fundo).
3. Rode os testes: `uv run pytest` (inclui checagem de descoberta de plugins).

---

## Comandos de desenvolvimento

```bash
just check               # Lint, tipos, dependências e código morto
uv run ruff format .     # Formata o código
uv run pytest            # Testes
```

`just check` executa Ruff, Pyright, Deptry e Vulture. A CI roda os mesmos
checks antes dos testes.

Use sempre `uv`. Nunca edite `pyproject.toml` à mão para dependências — use
`uv add` / `uv remove`. Commits seguem Conventional Commits (`feat:`, `fix:`, …).
