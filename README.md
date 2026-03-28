# 🎬 ani-tupi

Assista anime e leia mangá direto do terminal sem anúncios! Interface CLI em português brasileiro com integração AniList.

> Estava cansado de anúncios, o ani-cli não tinha conteúdo em português brasileiro e não havia leitor de mangá decente no terminal, então criei esta ferramenta.

## 📺 Demo no YouTube
[![Demo](https://img.youtube.com/vi/eug6gKLTD3I/maxresdefault.jpg)](https://youtu.be/eug6gKLTD3I)

## 🚀 Instalação Rápida

### Instalação com Um Comando (Recomendado)

A forma mais fácil de instalar - execute apenas um comando:

```bash
curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/master/install.sh | bash
```

Ou se preferir salvar o script primeiro:

```bash
curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/master/install.sh -o install.sh
bash install.sh
```

**O instalador faz automaticamente:**
- ✅ Detecta seu sistema (Linux, macOS, WSL)
- ✅ Verifica dependências (git, Python 3.12+)
- ✅ Instala UV se necessário
- ✅ Clona o repositório
- ✅ Instala ani-tupi como CLI global
- ✅ Configura o PATH automaticamente

**Requisitos do instalador:**
- `curl` - para baixar o script
- `git` - para clonar o repositório
- `Python 3.12+` - será detectado automaticamente

### Instalação CLI Global (Alternativa)

Instala `ani-tupi` e `manga-tupi` como comandos globais - use em qualquer lugar do sistema!

**Requisito:** Apenas Python 3.12+ (UV é instalado automaticamente pelo script)

```bash
# Clone o repositório
git clone https://github.com/levyvix/ani-tupi
cd ani-tupi

# Execute o instalador
python3 install-cli.py
```

**O instalador faz automaticamente:**
- ✅ Instala UV se não estiver presente
- ✅ Instala ani-tupi como ferramenta global usando UV
- ✅ Configura comandos `ani-tupi` e `manga-tupi`
- ✅ Mostra instruções para adicionar ao PATH se necessário

---

## ⚡ Primeiros Passos - Comandos Essenciais

Após instalar, estes são seus primeiros comandos:

```bash
# 1. Buscar e assistir anime
ani-tupi

# 2. Continuar último anime (salvo no histórico)
ani-tupi --continue-watching
ani-tupi -c

# 3. Buscar anime específico
ani-tupi --query "dandadan"
ani-tupi -q "dandadan"

# 4. Configurar AniList (sincronização automática)
ani-tupi anilist auth      # Login (apenas uma vez)
ani-tupi anilist           # Navegar listas + trending

# 5. Ler mangá
manga-tupi

# 6. Modo debug (mostra logs detalhados)
ani-tupi --debug

# 7. Ajuda
ani-tupi --help
```

### Testando a Instalação

```bash
# Verificar se instalou corretamente
ani-tupi --help

# Testar busca básica (sem AniList)
ani-tupi -q "naruto"

# Testar integração AniList (opcional)
ani-tupi anilist auth
ani-tupi anilist           # Ver menu com listas
```

---

## 💻 Como Usar

### Fluxo Básico

1. **Abrir** - `ani-tupi`
2. **Buscar** - Digite nome do anime (fuzzy search automática)
3. **Selecionar** - Use setas (↑↓) e Enter
4. **Assistir** - Player abre automaticamente
5. **Sincronizar** - Progresso salvo automaticamente (local + AniList se autenticado)

### Com AniList (Recomendado)

```bash
# 1. Fazer login (30 segundos, apenas uma vez)
ani-tupi anilist auth

# 2. Usar normalmente
ani-tupi anilist           # Ver listas + trending
ani-tupi -q "anime-name"   # Busca também sincroniza
ani-tupi -c                # Continua do último episódio

# Tudo sincroniza automaticamente! ✨
```

### Atalhos Durante Reprodução

| Atalho | Ação |
|--------|------|
| `Shift+N` | Próximo episódio |
| `Shift+P` | Episódio anterior |
| `Shift+M` | Marcar e voltar ao menu |
| `Shift+A` | Ativar auto-play |
| `ESC` | Voltar |

---

## 📋 Requisitos

- **Python 3.12+** (obrigatório)
- **mpv** (player de vídeo)
- **Zathura** (leitor de PDF para mangá - recomendado)
- **Firefox** (opcional, para alguns scrapers)
- **git** (para clonar o repositório)

### Instalando dependências

#### Linux (Arch)
```bash
# Instalar dependências do sistema
sudo pacman -S python mpv zathura firefox git libxml2 libvpx flite webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Linux (Ubuntu/Debian)
```bash
# Instalar dependências do sistema
sudo apt install python3 mpv zathura firefox git libxml2 libvpx libflite1 webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Linux (Fedora)
```bash
# Instalar dependências do sistema
sudo dnf install python3 mpv zathura firefox git libxml2 libvpx flite webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### macOS
```bash
# Instalar dependências do sistema
brew install python@3.12 mpv zathura firefox git

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Windows
Recomendamos usar [Chocolatey](https://chocolatey.org/install):
```powershell
# Como administrador
choco install python mpv zathura firefox git

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

**Nota:** Zathura é primariamente para Linux. No Windows, o sistema detectará automaticamente outros leitores de PDF instalados (Adobe Reader, SumatraPDF, etc).

### Modo Desenvolvimento

Para desenvolvedores - roda sem instalar globalmente:

```bash
git clone https://github.com/levyvix/ani-tupi
cd ani-tupi
uv sync                # Instala dependências
uv run ani-tupi        # Executa sem instalar
uv run main.py --debug # Modo debug
```

## 📦 Outras Opções de Instalação

### Instalação Manual

Se preferir instalar manualmente com UV:

```bash
# 1. Instale UV (se não tiver)
curl -LsSf https://astral.sh/uv/install.sh | sh         # Linux/macOS
# ou: irm https://astral.sh/uv/install.ps1 | iex        # Windows PowerShell

# 2. Clone e instale
git clone https://github.com/levyvix/ani-tupi
cd ani-tupi
uv tool install .
```

## ✨ Novos Recursos (Fevereiro 2025)

### 🎬 Airing Episodes - Descubra Novos Episódios
Veja automaticamente quais animes da sua lista AniList têm novos episódios no ar!

- **Tab "🎬 Novos Episódios"** no menu AniList
- Mostra quanto você está atrasado em cada anime (gap em episódios)
- Ordena por urgência (animes com maior atraso primeiro)
- **Grace period de 60 dias**: animes que terminaram de ser transmitidos continuam visíveis por 60 dias, para você não perder o fio da meada
- Selecione para assistir diretamente

**Exemplo:**
```
(2 atrasado) Frieren S2 - Anime finalizado, você viu 26/28 ⭐91%
(3 atrasado) Jujutsu Kaisen - Próximo Ep 25 sai em 2d 4h, você viu 22 ⭐82%
Blue Lock - Próximo Ep 11 sai em 5d, você viu 11 ⭐75%
```

### 🏠 Biblioteca Local - Assistir Offline
Baixe episódios para assistir depois, sem internet!

- **Tab "📂 Biblioteca Local"** no menu principal
- Organize episódios por anime
- Range flexível: `5`, `1-12`, `5-`, `-12`
- Configuração de paralelismo de downloads

**Ambiente:**
```bash
export ANI_TUPI__ANIME__DOWNLOAD_DIRECTORY="~/Videos/Anime"
export ANI_TUPI__ANIME__MAX_PARALLEL_DOWNLOADS=4
export ANI_TUPI__ANIME__VIDEO_FORMAT="mp4"
```

### 🔍 Busca Incremental com Histórico
Resultados mais precisos com busca progressiva!

- Digitar query e ani-tupi refina resultados incrementalmente
- Mostra historicamente todas as buscas anteriores
- Menu com navegação por histórico
- Melhor experiência para títulos longos/ambíguos

---

## ✨ Integração com AniList (Recomendado!)

A integração com [AniList.co](https://anilist.co) permite sincronizar automaticamente seu progresso ao assistir anime e ler mangá.

### 📺 Anime
- 📈 **Trending** - Descubra os animes mais populares do momento
- 📺 **Watching** - Continue de onde parou (lista AniList)
- 📋 **Planning** - Veja animes que você planeja assistir
- ✅ **Completed** - Histórico de animes completos
- 🔄 **Sincronização automática** - Progresso atualiza no AniList após cada episódio
- 📝 **Adição automática à Watching** - Adiciona anime à sua lista ao começar a assistir

### 📚 Manga
- 📚 **Trending Manga** - Descubra os mangás mais populares do momento
- 📖 **Reading** - Acesse sua lista "Lendo" do AniList
- 🔄 **Sincronização de capítulos** - Atualiza progresso no AniList após confirmar leitura
- 📋 **Status unificados** - Veja animes e mangás juntos nas listas

### 💾 Recursos
- **Mapeamento inteligente** - Lembra do título correto para cada anime/mangá
- **Cache inteligente** - Carrega listas instantaneamente
- **Menu de conta** - Veja seu perfil e estatísticas

**Setup rápido:**
```bash
ani-tupi anilist auth      # Login (apenas uma vez)
ani-tupi anilist           # Navegar listas + trending
```

Mesmo método usado por [viu-media](https://github.com/viu-media/viu) - simples e confiável!

### Atalhos Durante Reprodução (MPV)

Durante a reprodução de episódios, você pode usar estes atalhos para navegação rápida:

| Atalho | Ação | Efeito | Feedback no Terminal |
|--------|------|--------|---------------------|
| `Shift+N` | Próximo | Marca como assistido e carrega próximo episódio | `▶️  Reproduzindo Episódio {N}` |
| `Shift+P` | Anterior | Volta para o episódio anterior | `⏪ Voltando para Episódio {N}` |
| `Shift+M` | Marcar e Menu | Marca como assistido e volta ao menu | `📋 Episódio {N} marcado - Retornando ao menu` |
| `Shift+R` | Recarregar | Recarrega o episódio atual | `🔄 Recarregando Episódio {N}` |
| `Shift+A` | Auto-play | Alterna auto-play: ao sair (q) vai para próximo episódio automaticamente | `🔄 Auto-play ATIVADO/DESATIVADO` |
| `Shift+T` | Trocar Áudio | Alterna entre legendado/dublado (se disponível) | `🔄 Alternando legendado/dublado (se disponível)` |

**Notas:**
- Todos os atalhos exibem feedback tanto no terminal quanto na tela do MPV (OSD)
- O progresso é salvo automaticamente no histórico local e sincronizado com AniList (se autenticado)
- **Auto-play (Shift+A):**
  - Alterna modo global para toda a sessão (funciona mesmo trocando de anime)
  - Por padrão: **desativado** ao iniciar o app
  - Quando **ativado**: ao sair do player com `q`, marca episódio como assistido e carrega próximo automaticamente
  - Quando **desativado**: ao sair com `q`, volta ao menu normalmente
- Use `q` para sair do player (com auto-play ativado, avança automaticamente; desativado, volta ao menu)

---

## 📚 Recursos Detalhados

### 📖 Ler Mangá

Leia mangá do MangaDex direto do terminal com integração AniList!

**Comando:** `manga-tupi`

**Fluxo rápido:**
1. Abra `manga-tupi`
2. Digite nome do manga (fuzzy search automática)
3. Escolha capítulo
4. Leia no seu leitor PDF favorito
5. Progresso sincroniza automaticamente com AniList

**Leitores suportados:** Zathura (⭐ recomendado), Evince, Okular, MuPDF, macOS Preview, xdg-open

**Configuração:**
```bash
export ANI_TUPI__MANGA__PDF_READER=zathura
export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=~/Mangas
export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
```

[Guia completo abaixo em "Integração AniList - Guia Completo"]

### 🎬 Airing Episodes (Novos Episódios)

Veja automaticamente quais animes da sua lista AniList têm novos episódios no ar!

- **Tab "🎬 Novos Episódios"** no menu AniList
- Mostra quanto você está atrasado em cada anime (gap em episódios)
- Ordena por urgência (animes com maior atraso primeiro)
- **Grace period de 60 dias**: animes recém-finalizados permanecem visíveis com o label "Anime finalizado, você viu X/Y" (configurável via `ANI_TUPI__AIRING__GRACE_PERIOD_DAYS`)
- Selecione para assistir diretamente

### 🏠 Biblioteca Local (Download & Offline)

Baixe episódios para assistir depois, sem internet!

- **Tab "📂 Biblioteca Local"** no menu principal
- Range flexível: `5`, `1-12`, `5-`, `-12`
- Downloads paralelos configuráveis
- Sincronização com AniList após playback

### 🔍 Busca Incremental

Resultados mais precisos com busca progressiva!

- Refina automaticamente ao digitar
- Histórico de buscas com navegação
- Melhor experiência para títulos longos/ambíguos

---

## 🔐 Integração AniList - Guia Completo

A integração com [AniList.co](https://anilist.co) permite sincronizar automaticamente seu progresso ao assistir anime e ler mangá. Funciona de forma transparente - após fazer login uma vez, tudo sincroniza automáticamente!

### Como Funciona

```
1. AUTENTICAÇÃO (Uma vez)
   → ani-tupi anilist auth
   → OAuth token salvo em ~/.local/state/ani-tupi/anilist_token.json

2. SINCRONIZAÇÃO (Automática)
   → Episódio/Capítulo termina
   → ani-tupi envia para AniList
   → Seu progresso atualiza em tempo real

3. NAVEGAÇÃO (Integrada)
   → ani-tupi anilist mostra suas listas
   → Selecione anime/manga
   → ani-tupi busca nos scrapers automaticamente
```

### Setup Inicial (5 minutos)

```bash
# 1. Autenticar (apenas uma vez)
ani-tupi anilist auth

# 2. Usar normalmente
ani-tupi anilist    # Ver menu com listas + trending
ani-tupi -q "anime" # Buscar também sincroniza
ani-tupi -c         # Continuar do último episódio
```

### Opções de Menu AniList

```bash
ani-tupi anilist
# 📈 Trending - Populares agora
# 📺 Watching - Seus animes atuais
# 📋 Planning - Para começar depois
# ✅ Completed - Já assistiu
# ⏸️ Paused / ❌ Dropped / 🔁 Rewatching
# 📚 Manga Reading / Planning / Completed
# 📊 Account - Ver perfil
```

### Mapeamento Inteligente (Busca Automática)

Problema: AniList tem "Demon Slayer", scraper tem "Kimetsu no Yaiba".
Solução: ani-tupi memoriza automaticamente!

**Primeira vez:** Seleciona anime → Sistema busca → Você escolhe → Salva mapeamento
**Próximas vezes:** Clica no anime → Abre direto, sem pergunta

Salvo em: `~/.local/state/ani-tupi/anilist_mappings.json`

### Segurança

- Token armazenado localmente (não enviado para terceiros)
- Permissões mínimas (apenas leitura/escrita de listas)
- Sem acesso a dados sensíveis
- Validade: ~6 meses

### Troubleshooting

**Token expirou:**
```bash
ani-tupi anilist auth  # Faça login novamente
```

**Mapeamento errado:**
```bash
rm ~/.local/state/ani-tupi/anilist_mappings.json  # Refaz na próxima vez
```

**Sincronização lenta:**
```bash
ani-tupi --debug  # Ver logs detalhados
```

---

### Modo Desenvolvimento

Se está desenvolvendo (sem instalação global):

```bash
uv run ani-tupi              # Executar
uv run main.py --debug       # Com debug
uv run main.py -q "naruto"   # Buscar direto
```

### Build para Distribuição

Para criar executável standalone (não precisa Python instalado):

```bash
uv run build.py
```

O executável será criado em `dist/ani-tupi` (Linux/macOS) ou `dist/ani-tupi.exe` (Windows), junto com a pasta `plugins/`.

## 🔧 Para Desenvolvedores

### Estrutura do Projeto
```
ani-tupi/
├── main.py              # Entry point para anime
├── manga_tupi.py        # Entry point para mangá (refatorado)
├── manga_service.py     # Service layer MangaDex (NEW)
├── loader.py            # Sistema de plugins
├── repository.py        # Repositório de dados
├── menu.py              # Interface do menu (Rich + InquirerPy)
├── loading.py           # Loading spinners (Rich)
├── video_player.py      # Integração com mpv
├── models.py            # Pydantic data models (anime + manga)
├── config.py            # Configuração centralizada (Pydantic)
├── anilist.py           # Cliente AniList GraphQL
├── anilist_menu.py      # Menu AniList
├── scraper_cache.py     # Cache de scrapers
├── plugins/             # Plugins de scraping
│   ├── animefire.py
│   └── animesonlinecc.py
├── install-cli.py       # Instalador CLI global (principal)
├── build.py             # Build executável standalone
├── monitor-actions.sh   # Monitor GitHub Actions
├── .github/workflows/   # CI/CD automático
│   ├── ci.yml           # Validação rápida
│   ├── build-test.yml   # Testes de build
│   └── release.yml      # Releases automáticas
└── pyproject.toml       # Configuração do projeto
```

### Comandos Úteis

```bash
# Instalar/Reinstalar CLI global
python3 install-cli.py
# ou: uv tool install --force .

# Desinstalar CLI global
uv tool uninstall ani-tupi

# Instalar dependências (desenvolvimento)
uv sync

# Buildar executável standalone
uv run build.py

# Adicionar nova dependência
uv add nome-do-pacote

# Adicionar dependência de desenvolvimento
uv add --dev nome-do-pacote
```

### Por que UV?

[UV](https://github.com/astral-sh/uv) é um gerenciador de pacotes Python extremamente rápido:
- ⚡ 10-100x mais rápido que pip
- 🔒 Lock file determinístico (`uv.lock`)
- 📦 Gerenciamento de venv automático
- 🌍 Multiplataforma (Linux, macOS, Windows)
- 🚀 Instalação zero-config

## 📦 Usando Release Pré-compilada

Se houver uma release disponível, você pode baixar o executável direto:

```bash
# Baixe a release do GitHub
# Dê permissão de execução (Linux/macOS)
chmod +x ./ani-tupi

# Execute
./ani-tupi
```

## 🐛 Problemas Conhecidos

### AnimesDigital falha: "Executable doesn't exist at /home/..."

**Causa:** Playwright browser binaries não estão instalados ou faltam dependências do sistema.

**Solução:**

```bash
# 1. Instale os binários do Playwright
uv run playwright install

# 2. Instale dependências do sistema para seu OS
```

**Para Arch Linux:**
```bash
sudo pacman -S libxml2 libvpx flite webkit2gtk-4.1 xdg-utils
```

**Para Ubuntu/Debian:**
```bash
sudo apt install libxml2 libvpx libflite1 webkit2gtk-4.1 xdg-utils
```

**Para Fedora:**
```bash
sudo dnf install libxml2 libvpx flite webkit2gtk-4.1 xdg-utils
```

**Para macOS:**
```bash
brew install libxml2 libvpx flite webkit2gtk
```

Depois de instalar, teste:
```bash
uv run python -c "from playwright.sync_api import sync_playwright; print('✓ Playwright funcionando')"
```

### "FileNotFoundError" ao salvar histórico
Corrigido na versão 0.1.0+. Atualize para a versão mais recente.

### MPV não abre
Verifique se o mpv está instalado:
```bash
mpv --version
```

## 🤝 Contribuindo

Contribuições são bem-vindas! Abra uma issue ou pull request.

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

## 📄 Licença

GPL-3.0 - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🎓 Propósito Educacional

**Este projeto é fornecido exclusivamente para fins educacionais e de pesquisa.**

ani-tupi foi desenvolvido como uma ferramenta didática para demonstrar:
- Arquitetura de aplicações em Python (MVCP)
- Web scraping e parsing de HTML
- Integração com APIs GraphQL
- Desenvolvimento de TUIs em Python
- Sistemas de plugins extensíveis
- Gestão de cache e requisições assíncronas

### Bases Legais para Manutenção Pública

Este projeto é mantido publicamente com base nas seguintes disposições legais:

#### 🇧🇷 Legislação Brasileira

**Lei Federal Nº 9.610/98 (Lei de Direitos Autorais) - Art. 46:**
> "Não constitui ofensa aos direitos autorais a utilização de obra intelectual em situações especificadas em lei, quando autorizada pelo titular dos direitos ou quando não há restrição ao direito de usar... **para fins de estudo ou pesquisa**..."

- **Art. 46, IV**: Permite reprodução para "fins exclusivamente escolares ou acadêmicos"
- **Art. 46, VIII**: Permite "o apanhado de trechos de obras, para fins de citação ou comentário crítico, desde que não represente concorrência com a exploração normal da obra..."

#### 🌍 Legislação Internacional

**DMCA (Digital Millennium Copyright Act) - Seção 1201(d):**
> "Para fins de segurança, pesquisa ou educação, a Biblioteca do Congresso pode examinar e autorizar contorno de proteção tecnológica..."

**Diretiva Europeia 2001/29/EC (Diretiva de Copyright):**
- Artigo 5(3) permite reprodução para fins de ilustração para fins educacionais
- Artigo 9 permite reprodução limitada para pesquisa

**Convenção de Berna (Tratado Internacional):**
- Artigo 10 permite uso de obras para fins educacionais e de pesquisa

#### ⚖️ Princípio Legal Aplicável: Fair Use / Uso Justo

Este projeto se beneficia do princípio de "Fair Use" (uso justo), que permite uso de conteúdo protegido quando:

1. **Propósito**: ✅ Educacional, não comercial
2. **Natureza**: ✅ Ferramenta de aprendizado técnico
3. **Quantidade**: ✅ Mínima necessária para demonstrar conceitos
4. **Impacto de Mercado**: ✅ Sem prejuízo comercial aos titulares originais

### Orientações de Uso

Este projeto é destinado para:
- ✅ **Aprendizado**: Estude como construir web scrapers e TUIs
- ✅ **Pesquisa**: Analise técnicas de integração com APIs
- ✅ **Educação**: Use como referência em cursos de Python
- ✅ **Desenvolvimento**: Base para seus próprios projetos educacionais

Este projeto **não é destinado para**:
- ❌ Redistribuição comercial de conteúdo
- ❌ Substituição dos serviços legítimos de streaming
- ❌ Contorno de proteções de direitos autorais com fins comerciais

### Aviso Legal

Ao usar este projeto, você concorda que:
- É responsável pela conformidade com as leis locais
- Compreende que este é um projeto educacional
- Não usará para fins comerciais ou prejudiciais
- Respeitará os direitos dos detentores de conteúdo

Para questões legais específicas em sua jurisdição, consulte um advogado especializado em direitos autorais.

## 🙏 Agradecimentos

- Comunidade anime brasileira
- Desenvolvedores do mpv
- Projeto ani-cli (inspiração)

---

## 📝 Changelog

### v0.3.0 (Fevereiro 2025) - Airing Episodes & Local Library

**🎬 Airing Episodes (Novos Episódios)**
- ✅ Novo tab "🎬 Novos Episódios" no menu AniList
- ✅ Lista animes em transmissão com gap de episódios
- ✅ Ordena por urgência (maior atraso primeiro)
- ✅ Mostra score e quanto você está atrasado
- ✅ Integração seamless com playback

**📂 Biblioteca Local (Download & Offline)**
- ✅ Tab "📂 Biblioteca Local" no menu principal
- ✅ Baixe episódios para assistir depois
- ✅ Range flexível: `5`, `1-12`, `5-`, `-12`
- ✅ Downloads paralelos configuráveis (1-16)
- ✅ Salva progresso local persistentemente
- ✅ Sincronização com AniList após playback

**🔍 Busca Incremental & Histórico**
- ✅ Busca progressiva com refinamento automático
- ✅ Histórico de buscas com navegação
- ✅ Melhor precisão para títulos ambíguos
- ✅ Menu inteligente para múltiplos resultados

**🔧 Melhorias de Robustez**
- ✅ Validação de fontes por prioridade (AnimesDigital > AnimesFire)
- ✅ Tratamento de falha em fonte fallback
- ✅ Homepage incremental search para AnimesDigital
- ✅ Suporte a episodes descobertos dinamicamente

**🐛 Correções**
- ✅ Fallback source now validates non-empty chapters
- ✅ AnimesDigital ?odr=1 parameter requirement documented
- ✅ Episode order sorting and deduplication
- ✅ Homepage search matching precision

### v0.2.0 (Dezembro 2025) - Refactor & Performance

**🔄 Trocar Fonte Durante Reprodução**
- ✅ Opção "🔄 Trocar fonte" no menu pós-episódio
- ✅ Alterna entre versões dublada/legendada/diferentes scrapers
- ✅ Útil quando a fonte atual não tem episódios mais recentes
- ✅ Mostra todas as variações encontradas para o anime base
- ✅ Disponível em busca normal e fluxo AniList

**🎵 Refatoração Manga CLI**
- ✅ Mangá refatorado para seguir MVCP (Model-View-Controller-Plugin)
- ✅ Service layer MangaDex com erro handling e cache
- ✅ Substituição de `input()` por Rich + InquirerPy menus
- ✅ Spinners de loading para API calls
- ✅ Histórico de leitura em JSON (`manga_history.json`)
- ✅ Resume hint "⮕ Retomar" mostra último capítulo lido
- ✅ Configuração centralizada com Pydantic (`config.py`)
- ✅ Pydantic data models para MangaMetadata, ChapterData, etc
- ✅ Cache de capítulos (24h padrão, configurável)
- ✅ Múltiplos idiomas (pt-br, en, ja padrão)

**⚡ Performance e Cache**
- ✅ Cache de episódios: carrega instantaneamente lista de episódios já visitados
- ✅ Cache de scrapers: resultados de busca salvos para acesso rápido
- ✅ Correção de crash ao usar cache de episódios
- ✅ Migração de Textual para Rich + InquirerPy (TUI 65% menor, 10x mais rápido)

**🎉 Melhorias AniList**
- ✅ Adição automática de anime à lista Watching ao começar a assistir
- ✅ Menu de conta AniList: veja perfil e estatísticas no terminal
- ✅ Melhoria na navegação: ESC para voltar, Q para sair
- ✅ Correção de FileNotFoundError ao executar CLI de fora da pasta do projeto

**🔧 Qualidade de Código**
- ✅ Aplicação completa de linting Ruff
- ✅ Melhorias de formatação e mensagens
- ✅ Adição de OpenSpec para documentação de mudanças

### v0.2.0 (Integração AniList Completa)

**🎉 Integração AniList**
- ✅ Autenticação OAuth com AniList.co
- ✅ Navegação por listas (Watching, Planning, Completed, etc)
- ✅ Visualização de trending anime
- ✅ Sincronização automática de progresso após assistir episódios
- ✅ Confirmação "assistiu até o final" antes de atualizar
- ✅ Mapeamento inteligente: salva título correto do scraper para cada anime
- ✅ Retoma automaticamente no episódio correto (AniList + histórico local)
- ✅ Busca flexível: tenta romaji primeiro, depois inglês
- ✅ Suporte a títulos bilíngues (romaji + inglês)

**🔧 Melhorias de UX**
- ✅ Menu de opções quando há progresso salvo (continuar ou escolher episódio)
- ✅ Navegação com ESC para voltar nos menus
- ✅ Indicadores visuais de progresso (episódio X/Y, rating)

### v0.1.0 (Base)
- ✅ Sistema de plugins para múltiplos scrapers
- ✅ Integração com mpv para reprodução
- ✅ Menu curses em português brasileiro
- ✅ Histórico local de episódios assistidos
- ✅ Suporte a modo debug
- ✅ Build com PyInstaller
- ✅ Instalação via UV tool

---

🎬 **Bom anime!**
