# 🎬 ani-tupi

Assista anime e leia mangá direto do terminal sem anúncios! Interface CLI em português brasileiro com integração AniList.

> Estava cansado de anúncios, o ani-cli não tinha conteúdo em português brasileiro e não havia leitor de mangá decente no terminal, então criei esta ferramenta.

## 📺 Demo no YouTube
[![Demo](https://img.youtube.com/vi/eug6gKLTD3I/maxresdefault.jpg)](https://youtu.be/eug6gKLTD3I)

## 🚀 Instalação Rápida

### Instalação com Um Comando (Recomendado)

A forma mais fácil de instalar - execute apenas um comando:

```bash
curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/main/install.sh | bash
```

Ou se preferir salvar o script primeiro:

```bash
curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/main/install.sh -o install.sh
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

**Depois de instalado, use:**
```bash
ani-tupi                      # Buscar e assistir anime
ani-tupi --continue-watching  # Continuar último anime
ani-tupi anilist auth         # Autenticar com AniList.co
ani-tupi anilist              # Navegar suas listas no AniList
manga-tupi                    # Ler mangá
```

### Modo Desenvolvimento

Para desenvolvedores - roda sem instalar globalmente:

```bash
git clone https://github.com/levyvix/ani-tupi
cd ani-tupi
uv sync                # Instala dependências
uv run ani-tupi        # Executa sem instalar
uv run main.py --debug # Modo debug
```

## ✨ Novos Recursos (Fevereiro 2025)

### 🎬 Airing Episodes - Descubra Novos Episódios
Veja automaticamente quais animes da sua lista AniList têm novos episódios no ar!

- **Tab "🎬 Novos Episódios"** no menu AniList
- Mostra quanto você está atrasado em cada anime (gap em episódios)
- Ordena por urgência (animes com maior atraso primeiro)
- Selecione para assistir diretamente

**Exemplo:**
```
Jujutsu Kaisen - Ep 25 aired, você viu 22 (3 atrasado) ⭐82%
Dandadan - Ep 18 aired, você viu 15 (3 atrasado) ⭐79%
Blue Lock - Ep 11 aired, você viu 11 (0 atrasado) ⭐75%
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

### ⭐ Integração com AniList (Recomendado!)

**Sincronize automaticamente seu progresso com [AniList.co](https://anilist.co)!**

ani-tupi agora possui integração completa com AniList, permitindo:

### 📺 Anime
- 📈 **Trending** - Descubra os animes mais populares do momento
- 📅 **Recentes** - Continue de onde parou (histórico local)
- 📺 **Watching** - Acesse sua lista "Assistindo" do AniList
- 📋 **Planning** - Veja animes que você planeja assistir
- ✅ **Completed** - Histórico de animes completos
- 🔄 **Sincronização automática** - Progresso atualiza no AniList após cada episódio
- 📝 **Adição automática à Watching** - Adiciona anime à sua lista ao começar a assistir

### 📚 Manga (Novo!)
- 📚 **Trending Manga** - Descubra os mangás mais populares do momento
- 🔍 **Buscar Manga** - Encontre mangás para adicionar à sua lista
- 📖 **Reading** - Acesse sua lista "Lendo" do AniList
- 🔄 **Sincronização de capítulos** - Atualiza progresso no AniList após confirmar leitura
- ✅ **Confirmação de capítulo** - Pergunta se leu até o final antes de sincronizar
- 📋 **Status unificados** - Veja animes e mangás juntos nas listas (Planning, Completed, etc.)

### 🔧 Recursos Gerais
- 💾 **Mapeamento inteligente** - Lembra do título correto do scraper para cada anime/mangá
- ⚡ **Cache de episódios/capítulos** - Carrega lista instantaneamente na segunda vez
- 🚀 **Cache de scrapers** - Resultados de busca salvos para acesso rápido
- 👤 **Menu de conta AniList** - Veja seu perfil e estatísticas
- 🎯 **Títulos bilíngues** - Veja nomes em romaji + inglês
- ⌨️ **Navegação rápida** - Use ESC para voltar, setas para navegar

**Setup rápido (30 segundos):**

```bash
# 1. Fazer login (apenas uma vez)
ani-tupi anilist auth

# 2. Navegar suas listas + trending
ani-tupi anilist

# 3. Assista normalmente - tudo sincroniza automaticamente! ✨
```

Mesmo método usado por [viu-media](https://github.com/viu-media/viu) - simples e confiável!

---

## 📋 Requisitos

- **Python 3.12+** (obrigatório)
- **mpv** (player de vídeo)
- **Zathura** (leitor de PDF para mangá - recomendado)
- **Firefox** (para scraping com Selenium)
- **geckodriver** (driver para Selenium + Firefox)
- **Playwright** (para scraping avançado com suporte a múltiplos browsers)
- **git** (para clonar o repositório)

### Instalando dependências

#### Linux (Arch)
```bash
# Instalar dependências do sistema
sudo pacman -S python mpv zathura firefox geckodriver git libxml2 libvpx flite webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Linux (Ubuntu/Debian)
```bash
# Instalar dependências do sistema
sudo apt install python3 mpv zathura firefox git
# Instale geckodriver separadamente ou compile:
# https://github.com/mozilla/geckodriver/releases

# Instalar dependências para Playwright
sudo apt install libxml2 libvpx libflite1 webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Linux (Fedora)
```bash
# Instalar dependências do sistema
sudo dnf install python3 mpv zathura firefox git geckodriver libxml2 libvpx flite webkit2gtk-4.1

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### macOS
```bash
# Instalar dependências do sistema
brew install python@3.12 mpv zathura firefox git geckodriver

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

#### Windows
Recomendamos usar [Chocolatey](https://chocolatey.org/install):
```powershell
# Como administrador
choco install python mpv zathura firefox git geckodriver

# Depois de clonar e instalar ani-tupi, instalar Playwright:
uv run playwright install
```

**Nota:** Zathura é primariamente para Linux. No Windows, o sistema detectará automaticamente outros leitores de PDF instalados (Adobe Reader, SumatraPDF, etc).

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

## 💻 Como Usar

### Comandos Básicos

Após instalação global:

```bash
# Assistir anime
ani-tupi

# Continuar assistindo último anime
ani-tupi --continue-watching
ani-tupi -c

# Buscar anime específico
ani-tupi --query "dandadan"
ani-tupi -q "dandadan"

# AniList - Sincronizar com AniList.co
ani-tupi anilist auth      # Fazer login (apenas uma vez)
ani-tupi anilist           # Navegar listas e trending

# Ler mangá (com integração AniList!)
ani-tupi manga

# Ver ajuda
ani-tupi --help
```

**AniList Integration:**
- `ani-tupi anilist auth` - Autentica com AniList.co (necessário apenas uma vez)
- `ani-tupi anilist` - Navega trending, watching, planning, completed e outras listas (anime + manga)
- `ani-tupi manga` - Lê mangás com sincronização automática de progresso
- Sincronização automática - Seu progresso atualiza automaticamente após assistir cada episódio/lê cada capítulo

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

### Ler Mangá

Leia mangá do MangaDex direto do terminal com integração AniList!

#### Fluxo de Leitura

```bash
# 1. Iniciar leitor de mangá
manga-tupi

# 2. Buscar manga (digite para filtrar)
# 3. Selecione manga das sugestões
# 4. Escolha o capítulo para ler
# 5. Sistema baixa imagens → Converte para PDF → Abre no leitor
# 6. Leia normalmente no seu leitor PDF favorito
# 7. Ao sair, seu progresso é salvo automaticamente
```

**O que acontece automaticamente:**
1. ✅ Busca manga no MangaDex usando sua query
2. ✅ Detecta seus capítulos disponíveis
3. ✅ Baixa imagens de alta qualidade
4. ✅ Converte para PDF multi-página (otimizado para leitura)
5. ✅ Abre no seu leitor PDF configurado (Zathura, Evince, etc)
6. ✅ Salva progresso de leitura em histórico local
7. ✅ Sincroniza com AniList (se autenticado)

**Features Completas:**
- 🔍 **Busca em tempo real**: Digite para procurar manga em MangaDex
- 📖 **Menu interativo**: Navegar com setas, ESC para voltar
- 💾 **Histórico de leitura**: Salva último capítulo lido
- ⮕ **Retomar leitura**: Hint mostra onde você parou
- 📄 **PDF automático**: Baixa imagens e cria PDF em segundos
- 🔄 **Cache inteligente**: Reutiliza PDFs já baixados
- 📱 **Múltiplos leitores**: Zathura, Evince, Okular, MuPDF, xdg-open
- ⚙️ **Altamente configurável**: Pasta de download, qualidade, idiomas
- ⏳ **Loading spinners**: Feedback visual durante downloads/conversão
- 🔗 **Integração AniList**: Sincroniza progresso automaticamente
- 🇵🇹 **Múltiplos idiomas**: pt-br, en, ja (configurável)

#### Configuração Avançada

```bash
# Pasta de download padrão é ~/Downloads
# Customizar com variáveis de ambiente:

export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=~/Mangas
export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
export ANI_TUPI__MANGA__LANGUAGES=pt-br,en,ja
export ANI_TUPI__MANGA__PDF_READER=zathura                # Forçar leitor específico
export ANI_TUPI__MANGA__PDF_QUALITY=85                    # Qualidade JPEG (1-100)
export ANI_TUPI__MANGA__DELETE_IMAGES_AFTER_PDF=false     # Deletar PNGs após PDF
export ANI_TUPI__MANGA__ZATHURA_AUTO_CONFIG=true          # Auto-configurar zoom fit-width
```

#### Leitores de PDF Suportados

O ani-tupi detecta automaticamente seu leitor de PDF instalado nesta ordem:

| Leitor | Plataforma | Auto-config | Keyboard-driven |
|--------|-----------|-------------|-----------------|
| **Zathura** ⭐ | Linux | ✅ Zoom fit-width | ✅ Otimizado |
| Evince | Linux/GNOME | ✅ | ⚠️ Mouse |
| Okular | Linux/KDE | ✅ | ⚠️ Mouse |
| MuPDF | Linux | ❌ | ✅ Minimalista |
| macOS Preview | macOS | ❌ | ⚠️ GUI |
| xdg-open | Linux (fallback) | ❌ | ⚠️ Padrão sistema |

**Dica:** Zathura é recomendado - leve, focado em teclado, com excelente suporte para PDFs.

#### Integração com AniList

Se você autenticou no AniList (`ani-tupi anilist auth`), o ani-tupi sincroniza automaticamente:

```bash
# O progresso atualiza no AniList quando você:
1. Seleciona um mangá da lista AniList
2. Confirma que leu até o final
3. Sai do leitor PDF

# Seu progresso sincroniza automaticamente para:
- Manga "Reading" → Episódio/Capítulo atual atualizado
- Score, notas, status atualizam em tempo real
```

#### Atalhos e Navegação

**Durante busca:**
- `↑/↓` - Navegar sugestões
- `Enter` - Selecionar manga
- `ESC` - Cancelar busca
- `Ctrl+C` - Sair

**Durante seleção de capítulo:**
- `↑/↓` - Navegar capítulos
- `Enter` - Selecionar capítulo
- `ESC` - Voltar

**No leitor PDF (Zathura):**
- `↑/↓` ou `Page Up/Page Down` - Navegar páginas
- `+/-` - Ajustar zoom
- `a` - Zoom fit-width
- `w` - Zoom fit-height
- `q` - Sair (progresso salvo)

#### Resolução de Problemas

**PDF não abre ou abre no app errado:**
```bash
# Force um leitor específico
export ANI_TUPI__MANGA__PDF_READER=zathura
uv run manga_tupi  # ou apenas: manga-tupi
```

**Imagens não baixam / erro de conexão:**
- MangaDex pode estar sobrecarregado (tente depois)
- Seu IP pode estar rate-limited (aguarde)
- Verificar conexão de internet

**PDF muito grande:**
```bash
# Reduzir qualidade (economiza ~60% espaço)
export ANI_TUPI__MANGA__PDF_QUALITY=65
```

**Limpar cache de mangás:**
```bash
# Remove PDFs em cache para liberar espaço
rm -rf ~/.local/state/ani-tupi/manga_chapters/
```

### Integração AniList - Guia Completo

A integração com [AniList.co](https://anilist.co) permite sincronizar automaticamente seu progresso ao assistir anime e ler mangá. Funciona de forma transparente - após fazer login uma vez, tudo sincroniza automáticamente!

#### 🔐 Como Funciona (Arquitetura)

```
1. AUTENTICAÇÃO (Uma vez)
   ↓
   ani-tupi anilist auth → Abre navegador → Você faz login
                        → Gera OAuth token → Salvo em ~/.local/state/ani-tupi/anilist_token.json
   ↓
2. SINCRONIZAÇÃO (Automática)
   ↓
   Você assistindo anime/lendo mangá → Episódio/Capítulo termina
                                    → ani-tupi detecta automaticamente
                                    → Envia GraphQL query para AniList
                                    → Seu progresso atualiza em tempo real
   ↓
3. NAVEGAÇÃO (Integrada)
   ↓
   ani-tupi anilist → Mostra suas listas do AniList
                   → Você seleciona anime/manga
                   → ani-tupi busca nos scrapers automaticamente
                   → Encontra o episódio exato onde você parou
```

#### ⚙️ Setup Inicial (5 minutos)

**Passo 1: Autenticar com AniList**

```bash
# Executa fluxo OAuth completo
ani-tupi anilist auth

# O que acontece:
# 1. Terminal mostra: "🔗 Abrindo navegador para autenticação..."
# 2. Seu navegador abre AniList.co
# 3. Você clica "Autorizar" para conceder acesso ao ani-tupi
# 4. AniList mostra token de autorização
# 5. Você cola no terminal do ani-tupi
# 6. Sistema salva token criptografado
```

**⚠️ Nota Importante:** O token é armazenado em `~/.local/state/ani-tupi/anilist_token.json`. Este arquivo é privado e contém sua autenticação!

**Passo 2: Verificar Autenticação**

```bash
# Mostra seu perfil AniList
ani-tupi anilist account

# Saída esperada:
# 👤 Seu Nome
# 📺 Watching: 25 anime
# 📚 Reading: 12 mangá
# ✅ Completed: 150 anime
# ... mais estatísticas
```

**Passo 3: Pronto!**

```bash
# Navegar suas listas e trending
ani-tupi anilist

# Assistir normalmente (sem fazer mais nada)
ani-tupi
```

Agora tudo sincroniza automaticamente!

#### 📺 Fluxo Completo de Anime com AniList

**Opção 1: Continuar de Onde Parou**

```bash
# Mostra últimos animes que você estava assistindo
ani-tupi anilist watching

# Seleciona manga com setas (↑↓)
# ani-tupi encontra automaticamente:
# - Onde você parou (último episódio assistido)
# - Qual scraper tem os novos episódios
# - Pula direto para próximo episódio

# Ao sair do player, progresso sincroniza automaticamente
```

**Opção 2: Descobrir Novo Anime**

```bash
# Mostra trending anime popular agora
ani-tupi anilist trending

# Ou busca sua lista de planejamento
ani-tupi anilist planning

# Ao selecionar e assistir, adiciona automaticamente
# à sua lista "Watching" e marca episódio como visto
```

**Opção 3: Menu Principal**

```bash
# Mostra dashboard com todas as opções
ani-tupi anilist

# Opções:
# 📈 Trending - Populares agora
# 📺 Watching - Seus animes atuais
# 📋 Planning - Para começar depois
# ✅ Completed - Já assistiu
# ⏸️ Paused - Pausado
# ❌ Dropped - Largou
# 🔁 Rewatching - Reassistindo
# 📊 Account - Ver perfil
```

#### 🔄 Como Funciona a Sincronização Automática

**Anime - Fluxo Automático:**

```
1. Você abre anime da lista AniList
2. Seleciona episódio
3. Assiste até o final
4. Sistema detecta: "🎬 Episódio 5 completo!"
5. Mostra pergunta:
   ✅ Assistiu até o final?
   [Sim] [Não] [Assistir novamente]
6. Você clica "Sim"
7. ani-tupi envia para AniList:
   - Seu anime ID
   - Episódio 5
   - Timestamp
8. AniList atualiza instantaneamente
9. Seu amigo vê: "User está assistindo Anime - Episódio 5/12"
```

**Mangá - Fluxo Automático:**

```
1. Você abre mangá do AniList
2. Lê capítulo no PDF
3. Sai do leitor (q)
4. Sistema pergunta:
   ✅ Leu até o final?
   [Sim] [Não]
5. Clica "Sim"
6. ani-tupi sincroniza:
   - Seu mangá ID
   - Capítulo X
   - Data de leitura
7. AniList atualiza lista "Reading"
```

**Sem Fazer Nada Manualmente** - tudo é automático!

#### 💾 Mapeamento Inteligente (Busca Automática)

Problema: AniList tem título "Demon Slayer", mas o scraper tem "Kimetsu no Yaiba".

**Solução:** ani-tupi memoriza automaticamente!

```
Primeira vez:
1. Seleciona anime AniList: "Demon Slayer"
2. Sistema busca em todos scrapers
3. Encontra 3 resultados similares
4. Você escolhe: "Kimetsu no Yaiba (AnimeFire)"
5. Sistema salva: "Demon Slayer" = "Kimetsu no Yaiba"

Próximas vezes:
1. Clica em "Demon Slayer" novamente
2. Sistema já sabe: usa AnimeFire direto
3. Pula para episódio certo automaticamente
   ⚡ Nenhuma busca, nenhuma pergunta
```

Mapeamento salvo em: `~/.local/state/ani-tupi/anilist_mappings.json`

#### 🔍 Busca Flexível

Se ani-tupi não encontra exato, tenta alternativas:

```
Exemplo: Procura "My Hero Academia Season 7"

Ordem de busca:
1. Tenta título romaji exato: "Boku no Hero Academia S7"
2. Tenta título inglês: "My Hero Academia Season 7"
3. Tenta busca fuzzy: "hero academia"
4. Mostra múltiplos resultados
5. Você escolhe qual é

Permite escolher entre:
- Diferentes scrapers (AnimeFire vs AnimesonlineCC)
- Diferentes versões (dublado vs legendado)
- Diferentes qualidades
```

#### ⏱️ Duração do Token OAuth

```
Token de autenticação:
- Validade: ~6 meses
- Após expirar: "❌ Autenticação inválida"
- Solução: ani-tupi anilist auth (fazer login novamente)
- Duração: 30 segundos
```

#### 🔒 Segurança e Privacidade

- **Token armazenado localmente:** `~/.local/state/ani-tupi/anilist_token.json`
- **Nunca enviado para terceiros** - apenas para AniList.co
- **Permissões mínimas** - apenas leitura/escrita de listas
- **Sem acesso a dados sensíveis** - senhas, emails, etc

#### 📊 Configuração Avançada

```bash
# Forçar re-autenticação (resetar token)
rm ~/.local/state/ani-tupi/anilist_token.json
ani-tupi anilist auth

# Resetar cache de mapeamentos (forçar busca novamente)
rm ~/.local/state/ani-tupi/anilist_mappings.json

# Desabilitar sincronização automática (ainda busca listas)
# Nota: Não há flag para isso atualmente, mas pode editar código

# Ver estatísticas completas do perfil
ani-tupi anilist account

# Limpar histórico local (mantém AniList intacto)
rm ~/.local/state/ani-tupi/anime_history.json
rm ~/.local/state/ani-tupi/manga_history.json
```

#### 🐛 Troubleshooting AniList

**"❌ Autenticação inválida"**
```bash
# Token expirou (válido por ~6 meses)
ani-tupi anilist auth
# Faça login novamente
```

**"⚠️ Não encontrou anime no AniList"**
```bash
# Mapeamento pode estar errado ou AniList não tem o anime
# Limpar e refazer:
rm ~/.local/state/ani-tupi/anilist_mappings.json

# Ou buscar manualmente:
ani-tupi -q "Naruto"  # Busca em scrapers
ani-tupi anilist       # Busca em AniList
```

**"⏸️ Sincronização lenta"**
```bash
# Pode estar em cache antigo
rm ~/.local/state/ani-tupi/anilist_cache.json

# Ou AniList API está sobrecarregada
# Tente mais tarde
```

**"🔀 Progresso não sincronizou"**
```bash
# Verificar logs:
ani-tupi --debug  # Modo debug mostra erros

# Causa comum: Internet caiu durante sincronização
# Solução: Ao abrir próximo episódio, sincroniza retroativamente
```

**"👤 Perfil não mostra"**
```bash
# Comando para ver perfil:
ani-tupi anilist account

# Se não mostra, verificar autenticação:
ani-tupi anilist auth
```

**Features:**
- 📈 **Trending**: Veja os animes mais populares do momento
- 📺 **Watching**: Continue de onde parou (se logado)
- 📋 **Planning**: Animes que você planeja assistir
- ✅ **Completed**: Histórico de animes completos
- ⏸️ **Paused** / ❌ **Dropped** / 🔁 **Rewatching**: Todas as suas listas
- 🔄 **Sincronização automática**: Progresso atualiza no AniList após assistir cada episódio
- 📝 **Adição automática à lista Watching**: Adiciona anime à sua lista ao começar a assistir
- 💾 **Mapeamento inteligente**: Salva o título correto do scraper para cada anime do AniList
- ⚡ **Cache de episódios**: Carrega lista de episódios instantaneamente na segunda vez
- 🚀 **Cache de scrapers**: Resultados de busca salvos para acesso rápido
- ✅ **Confirmação de progresso**: Pergunta se você assistiu até o final antes de sincronizar
- 👤 **Menu de conta AniList**: Veja seu perfil e estatísticas diretamente no terminal
- 🎯 **Continuar de onde parou**: Retoma automaticamente no episódio certo (AniList + histórico local)
- 🔍 **Busca flexível**: Tenta romaji primeiro, depois inglês se não encontrar
- 📝 **Múltiplas fontes**: Se encontrar múltiplos resultados, deixa você escolher o correto
- 🔄 **Trocar fonte durante reprodução**: Mude entre versões dublada/legendada/diferentes scrapers após assistir um episódio quando a fonte atual não tiver novos episódios disponíveis

**Resumo Rápido:**
1. Faça login uma vez: `ani-tupi anilist auth`
2. Use seu AniList normalmente: `ani-tupi anilist`
3. Tudo sincroniza automaticamente! ✨

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

### Vídeo não abre (mostra "Buscando vídeo..." e pula para menu)

**Causa:** Geckodriver não está instalado ou não está no PATH.

**Solução:**

**Arch:**
```bash
sudo pacman -S geckodriver
```

**Ubuntu/Debian:**
```bash
# Método 1: Via repositório (se disponível)
sudo apt install firefox-geckodriver
# Ou compile manualmente:
wget https://github.com/mozilla/geckodriver/releases/download/v0.33.3/geckodriver-v0.33.3-linux64.tar.gz
tar -xvf geckodriver-v0.33.3-linux64.tar.gz
sudo mv geckodriver /usr/local/bin/
sudo chmod +x /usr/local/bin/geckodriver
```

**Verificar instalação:**
```bash
geckodriver --version
which geckodriver
```

### "FileNotFoundError" ao salvar histórico
Corrigido na versão 0.1.0+. Atualize para a versão mais recente.

### MPV não abre
Verifique se o mpv está instalado:
```bash
mpv --version
```

### Firefox não encontrado
Certifique-se de que o Firefox está no PATH do sistema.

**Verificar:**
```bash
which firefox
firefox --version
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
