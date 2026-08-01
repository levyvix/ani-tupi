# 🎬 ani-tupi

Assista anime e leia mangá direto do terminal sem anúncios! Interface CLI em português brasileiro com integração AniList.

[![PyPI](https://img.shields.io/pypi/v/ani-tupi)](https://pypi.org/project/ani-tupi/)
[![Python](https://img.shields.io/pypi/pyversions/ani-tupi)](https://pypi.org/project/ani-tupi/)

> Estava cansado de anúncios, o ani-cli não tinha conteúdo em português brasileiro e não havia leitor de mangá decente no terminal, então criei esta ferramenta.

## 📺 Demo no YouTube
[![Demo](https://img.youtube.com/vi/eug6gKLTD3I/maxresdefault.jpg)](https://youtu.be/eug6gKLTD3I)

## 📋 Requisitos

- **Python 3.12+** (obrigatório)
- **mpv** (player de vídeo)
- **Zathura** (leitor de PDF para mangá - recomendado)
- **Chromium** (ou Google Chrome — necessário para os scrapers de mangá que usam Selenium)
- **git** (opcional — só necessário para clonar o repositório ou usar `install.sh`)

### Instalando dependências

#### Linux (Arch)
```bash
# Instalar dependências do sistema
sudo pacman -S python mpv zathura chromium git
```

#### Linux (Ubuntu/Debian)
```bash
# Instalar dependências do sistema
sudo apt install python3 mpv zathura chromium-browser git
```

#### Linux (Fedora)
```bash
# Instalar dependências do sistema
sudo dnf install python3 mpv zathura chromium git
```

#### macOS
```bash
# Instalar dependências do sistema
brew install python@3.12 mpv zathura chromium git
```

#### Windows
Recomendamos usar [Chocolatey](https://chocolatey.org/install):
```powershell
# Como administrador
choco install python mpv zathura googlechrome git
```

**Nota:** Zathura é primariamente para Linux. No Windows, o sistema detectará automaticamente outros leitores de PDF instalados (Adobe Reader, SumatraPDF, etc).

## 🚀 Instalação Rápida

### Via [PyPI](https://pypi.org/project/ani-tupi/) (Recomendado)

Instale o pacote Python com **uv** ou **pip** a partir do [PyPI](https://pypi.org/project/ani-tupi/). Você ainda precisa das [dependências de sistema](#-requisitos) (`mpv`, leitor de PDF, etc.) — elas não vêm com o pacote PyPI.

```bash
# Recomendado: instala ani-tupi e manga-tupi como ferramentas globais
uv tool install ani-tupi

# Alternativa: uv em um venv
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install ani-tupi

# Alternativa: pip (dentro de um venv)
pip install ani-tupi
```

Atualizar para a versão mais recente:

```bash
uv tool install --upgrade ani-tupi
# ou, dentro do venv:
uv pip install --upgrade ani-tupi
# ou: pip install --upgrade ani-tupi
```

### Via Homebrew (macOS e Linux)

```bash
brew tap levyvix/ani-tupi
brew install ani-tupi
```

Atualizar:

```bash
brew upgrade ani-tupi
```

> Requer `mpv` instalado: `brew install mpv`

### Instalação com Um Comando (Alternativa)

Script completo com clone do repositório — útil se você prefere o bootstrap automático ou está contribuindo com o código:

```bash
curl -sSL https://raw.githubusercontent.com/levyvix/ani-tupi/master/install.sh | bash
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

### Mais exemplos de uso da CLI

```bash
# Buscar um anime e abrir o seletor de episódios
ani-tupi -q "one piece"

# Buscar e ir direto para um episódio específico
ani-tupi -q "one piece" -e 1100

# Escolher uma temporada específica
ani-tupi -q "jujutsu kaisen" -S 2

# Ir direto para episódio de uma temporada específica
ani-tupi -q "jujutsu kaisen" -S 2 -e 5

# Continuar de onde parou
ani-tupi -c

# Continuar o último anime, mas trocar para outro episódio
ani-tupi -c -e 12

# Continuar o último anime, mas trocar de temporada
ani-tupi -c -S 2

# Sortear um anime da sua lista do AniList e reproduzir
ani-tupi --random
ani-tupi -r

# Listar fontes de anime disponíveis
ani-tupi --list-sources

# Limpar todo o cache
ani-tupi --clear-cache

# Limpar cache de um anime específico
ani-tupi --clear-cache "dandadan"

# Abrir o fluxo de mangá pelo comando principal
ani-tupi --manga
ani-tupi -m

# Ver versão local e comparar com a release remota
ani-tupi --version

# Verificar atualização pela CLI
ani-tupi update
```

## ⚙️ Configurar pela CLI

Agora você pode configurar o `ani-tupi` sem editar `models/config.py`:

```bash
ani-tupi config
```

No menu `ani-tupi config`:
- cada categoria representa uma classe de settings (`AnilistSettings`, `CacheSettings`, etc.)
- você escolhe a chave com `valor atual + descrição` do que ela controla
- antes de editar, a CLI mostra a documentação daquela configuração
- você informa o novo valor e confirma salvamento
- as alterações são persistidas no usuário em `~/.config/ani-tupi/settings.json`

### Precedência de configuração

O carregamento segue esta ordem:

1. Variáveis de ambiente (`ANI_TUPI__...`)
2. Configuração salva via `ani-tupi config`
3. Valores padrão da aplicação

Se uma chave tiver variável de ambiente ativa, o menu mostra aviso de precedência.

**💡 Dica para melhores resultados de busca:**
Tente usar o nome do anime em japonês ou romaji para maior precisão. Por exemplo:
- Em vez de "Attack on Titan", tente "Shingeki no Kyojin"
- Em vez de "My Hero Academia", tente "Boku no Hero Academia"
- Em vez de "Demon Slayer", tente "Kimetsu no Yaiba"
- Em vez de "Jujutsu Kaisen", mantenha como está (já é o título original)

---

### Atalhos Durante Reprodução

| Atalho | Ação |
|--------|------|
| `Shift+N` | Próximo episódio |
| `Shift+P` | Episódio anterior |
| `Shift+M` | Marcar como assistido e abrir menu |
| `Shift+R` | Recarregar o episódio atual |
| `Shift+F` | Trocar de fonte (próxima fonte do episódio) |
| `Shift+A` | Ativar auto-play |
| `Shift+T` | Alternar legendado/dublado (se disponível) |

---

## ✨ Features

### 🎬 Novos Episódios (AniList)
- Mostra animes com episódio novo e quanto você está atrasado
- Ordena por urgência e permite abrir para assistir direto
- Mantém títulos recém-finalizados por 60 dias

### 🏠 Biblioteca Local (Offline)
- Baixe episódios e organize por anime
- Suporta range de download (`5`, `1-12`, `5-`, `-12`)
- Paralelismo configurável para acelerar downloads

**Configuração rápida:**
```bash
export ANI_TUPI__ANIME__DOWNLOAD_DIRECTORY="~/Videos/Anime"
export ANI_TUPI__ANIME__MAX_PARALLEL_DOWNLOADS=4
export ANI_TUPI__ANIME__VIDEO_FORMAT="mp4"
```

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

---

## 📖 Ler Mangá

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

---

### Troubleshooting

**Token expirou:**
```bash
ani-tupi anilist auth  # Faça login novamente
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

## 🔧 Para Desenvolvedores

### Comandos Úteis

```bash
# Instalar/Reinstalar CLI global (PyPI)
uv tool install --upgrade ani-tupi

# Instalar a partir do checkout local (desenvolvimento)
python3 install-cli.py
# ou: uv tool install --force .

# Desinstalar CLI global
uv tool uninstall ani-tupi

# Instalar dependências (desenvolvimento)
uv sync

# Adicionar nova dependência
uv add nome-do-pacote

# Adicionar dependência de desenvolvimento
uv add --dev nome-do-pacote
```

### Publicação PyPI (mantenedores)

Secrets necessários no repositório GitHub:

| Secret | Uso |
|--------|-----|
| `TESTPYPI_API_TOKEN` | Upload para [TestPyPI](https://test.pypi.org) |
| `PYPI_API_TOKEN` | Upload para PyPI oficial (após validação) |

Variável de repositório:

| Variável | Valor | Efeito |
|----------|-------|--------|
| `PYPI_PUBLISH_ENABLED` | `true` | Habilita upload para PyPI no workflow de release |

Fluxo recomendado:

1. Criar token em [test.pypi.org](https://test.pypi.org/manage/account/token/) e salvar como `TESTPYPI_API_TOKEN`
2. Disparar **Actions → Publish TestPyPI** (`workflow_dispatch`) e confirmar instalação
3. Após validação, configurar `PYPI_API_TOKEN` e definir `PYPI_PUBLISH_ENABLED=true`

### Por que UV?

[UV](https://github.com/astral-sh/uv) é um gerenciador de pacotes Python extremamente rápido:
- ⚡ 10-100x mais rápido que pip
- 🔒 Lock file determinístico (`uv.lock`)
- 📦 Gerenciamento de venv automático
- 🌍 Multiplataforma (Linux, macOS, Windows)
- 🚀 Instalação zero-config

## 🐛 Problemas Conhecidos

### "FileNotFoundError" ao salvar histórico
Corrigido na versão 0.1.0+. Atualize para a versão mais recente.

### MPV não abre
Verifique se o mpv está instalado:
```bash
mpv --version
```

## 🤝 Contribuindo

Contribuições são bem-vindas! Abra uma issue ou pull request.

> 📖 **Antes de mexer no código, leia [`CONTRIBUTING.md`](./CONTRIBUTING.md)** —
> especialmente a seção **Filosofia de fontes**, que explica as decisões do autor
> sobre priorização de fontes (velocidade, qualidade HD e legenda) e as regras
> que todo PR deve preservar.

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
- [Eduardo Nery](https://github.com/eduardonery1) — autor do projeto original [ani-tupi](https://github.com/eduardonery1/ani-tupi), do qual este fork é derivado
