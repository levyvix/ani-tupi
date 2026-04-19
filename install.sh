#!/bin/bash

set -e

REPO_URL="https://github.com/levyvix/ani-tupi"
INSTALL_DIR="$HOME/.local/ani-tupi"
BIN_DIR="$HOME/.local/bin"

color_red='\033[0;31m'
color_green='\033[0;32m'
color_yellow='\033[1;33m'
color_blue='\033[0;34m'
color_reset='\033[0m'

log_info() {
    echo -e "${color_blue}[INFO]${color_reset} $1"
}

log_success() {
    echo -e "${color_green}[✓]${color_reset} $1"
}

log_warn() {
    echo -e "${color_yellow}[⚠]${color_reset} $1"
}

log_error() {
    echo -e "${color_red}[✗]${color_reset} $1"
}

detect_platform() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
            echo "wsl"
        else
            echo "linux"
        fi
    else
        echo "unsupported"
    fi
}

check_command() {
    command -v "$1" >/dev/null 2>&1
}

check_python_version() {
    if check_command python3; then
        local version
        version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)

        if [[ "$major" -eq 3 && "$minor" -ge 12 ]]; then
            return 0
        fi
    fi
    return 1
}

install_uv() {
    log_info "Instalando UV..."

    if check_command uv; then
        log_success "UV já está instalado"
        return 0
    fi

    if check_command curl; then
        log_info "Baixando instalador do UV..."
        curl -LsSf https://astral.sh/uv/install.sh | sh

        if [[ -f "$HOME/.local/bin/uv" ]]; then
            export PATH="$HOME/.local/bin:$PATH"
            log_success "UV instalado com sucesso"
            return 0
        fi
    fi

    if check_command pip3 || check_command pip; then
        local pip_cmd="pip3"
        check_command pip3 || pip_cmd="pip"

        log_info "Instalando UV via $pip_cmd..."
        "$pip_cmd" install --user uv

        if [[ "$OSTYPE" == "darwin"* ]]; then
            local python_version
            python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            local scripts_dir="$HOME/Library/Python/${python_version}/bin"
        else
            local scripts_dir="$HOME/.local/bin"
        fi

        if [[ -f "$scripts_dir/uv" ]]; then
            export PATH="$scripts_dir:$PATH"
            log_success "UV instalado com sucesso"
            return 0
        fi
    fi

    return 1
}

check_dependencies() {
    local missing=()

    if ! check_command git; then
        missing+=("git")
    fi

    if ! check_python_version; then
        missing+=("Python 3.12+")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Dependências faltando: ${missing[*]}"
        return 1
    fi

    log_success "Todas as dependências estão instaladas"
    return 0
}

clone_repo() {
    log_info "Clonando repositório..."

    if [[ -d "$INSTALL_DIR" ]]; then
        log_warn "Diretório já existe. Atualizando..."
        cd "$INSTALL_DIR"
        git pull origin main 2>/dev/null || git pull origin master 2>/dev/null
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    log_success "Repositório clonado/atualizado"
}

install_cli() {
    log_info "Instalando ani-tupi como CLI global..."

    cd "$INSTALL_DIR"

    if check_command uv; then
        uv tool install --reinstall .
        local result=$?
    else
        log_error "UV não está disponível"
        return 1
    fi

    if [[ $result -eq 0 ]]; then
        log_success "ani-tupi instalado com sucesso!"
        return 0
    else
        log_error "Falha ao instalar ani-tupi"
        return 1
    fi
}

add_to_path() {
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        log_info "Adicionando $BIN_DIR ao PATH..."

        local shell_rc=""
        if [[ -n "$ZSH_VERSION" ]]; then
            shell_rc="$HOME/.zshrc"
        elif [[ -n "$BASH_VERSION" ]]; then
            shell_rc="$HOME/.bashrc"
        fi

        if [[ -n "$shell_rc" ]]; then
            if ! grep -q "$BIN_DIR" "$shell_rc" 2>/dev/null; then
                echo "" >> "$shell_rc"
                echo "# ani-tupi" >> "$shell_rc"
                echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$shell_rc"
                log_success "PATH configurado em $shell_rc"
                log_warn "Execute: source $shell_rc"
            fi
        fi
    fi

    export PATH="$BIN_DIR:$PATH"
}

main() {
    echo -e "${color_blue}╔═══════════════════════════════════════╗${color_reset}"
    echo -e "${color_blue}║      Instalador ani-tupi            ║${color_reset}"
    echo -e "${color_blue}╚═══════════════════════════════════════╝${color_reset}"
    echo ""

    local platform
    platform=$(detect_platform)

    if [[ "$platform" == "unsupported" ]]; then
        log_error "Plataforma não suportada"
        exit 1
    fi

    log_info "Plataforma detectada: $platform"
    echo ""

    if ! check_dependencies; then
        log_error "Por favor, instale as dependências faltantes e tente novamente"
        exit 1
    fi
    echo ""

    if ! install_uv; then
        log_error "Não foi possível instalar UV"
        exit 1
    fi
    echo ""

    clone_repo
    echo ""

    if ! install_cli; then
        exit 1
    fi
    echo ""

    add_to_path
    echo ""

    echo -e "${color_green}═══════════════════════════════════════${color_reset}"
    echo -e "${color_green}  Instalação concluída com sucesso!${color_reset}"
    echo -e "${color_green}═══════════════════════════════════════${color_reset}"
    echo ""
    echo "Comandos disponíveis:"
    echo "  ani-tupi              - Assistir anime"
    echo "  ani-tupi --continue   - Continuar último anime"
    echo "  ani-tupi anilist     - Integração AniList"
    echo "  manga-tupi            - Ler mangá"
    echo ""
    echo "Para começar, execute:"
    echo "  ani-tupi"
    echo ""
}

main "$@"
