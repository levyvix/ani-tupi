# 🎬 ani-tupi

Assista anime direto do terminal sem anúncios! Interface CLI em português brasileiro.

> Estava cansado de anúncios e o ani-cli não tinha conteúdo em português brasileiro, então criei esta ferramenta.

Para ver mangás, confira: [manga-tupi](https://github.com/manga-tupi)

## 📺 Demo no YouTube
[![Demo](https://img.youtube.com/vi/eug6gKLTD3I/maxresdefault.jpg)](https://youtu.be/eug6gKLTD3I)

## 📋 Requisitos

- **Python 3.12+** (obrigatório)
- **mpv** (player de vídeo)
- **Firefox** (para scraping)
- **git** (para clonar o repositório)

### Instalando dependências

#### Linux (Ubuntu/Debian)
```bash
sudo apt install python3 mpv firefox git
```

#### Linux (Fedora)
```bash
sudo dnf install python3 mpv firefox git
```

#### macOS
```bash
brew install python@3.12 mpv firefox git
```

#### Windows
Recomendamos usar [Chocolatey](https://chocolatey.org/install):
```powershell
# Como administrador
choco install python mpv firefox git
```

## 🚀 Instalação

### Instalação CLI Global (Recomendado)

Instala `ani-tupi` e `manga-tupi` como comandos globais - use em qualquer lugar do sistema!

**Requisito:** Apenas Python 3.12+ (UV é instalado automaticamente pelo script)

```bash
# Clone o repositório
git clone https://github.com/eduardonery1/ani-tupi
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
manga-tupi                    # Ler mangá
```

### Instalação Manual

Se preferir instalar manualmente com UV:

```bash
# 1. Instale UV (se não tiver)
curl -LsSf https://astral.sh/uv/install.sh | sh         # Linux/macOS
# ou: irm https://astral.sh/uv/install.ps1 | iex        # Windows PowerShell

# 2. Clone e instale
git clone https://github.com/eduardonery1/ani-tupi
cd ani-tupi
uv tool install .
```

### Modo Desenvolvimento

Para desenvolvedores - roda sem instalar globalmente:

```bash
git clone https://github.com/eduardonery1/ani-tupi
cd ani-tupi
uv sync                # Instala dependências
uv run ani-tupi        # Executa sem instalar
uv run main.py --debug # Modo debug
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

# Ler mangá
manga-tupi

# Ver ajuda
ani-tupi --help
```

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
├── manga_tupi.py        # Entry point para mangá
├── loader.py            # Sistema de plugins
├── repository.py        # Repositório de dados
├── menu.py              # Interface do menu
├── video_player.py      # Integração com mpv
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

### "FileNotFoundError" ao salvar histórico
Corrigido na versão 0.1.0+. Atualize para a versão mais recente.

### MPV não abre
Verifique se o mpv está instalado:
```bash
mpv --version
```

### Firefox não encontrado
Certifique-se de que o Firefox está no PATH do sistema.

## 🤝 Contribuindo

Contribuições são bem-vindas! Abra uma issue ou pull request.

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

## 📄 Licença

GPL-3.0 - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🙏 Agradecimentos

- Comunidade anime brasileira
- Desenvolvedores do mpv
- Projeto ani-cli (inspiração)

---

🎬 **Bom anime!**
