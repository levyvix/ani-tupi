#!/bin/bash
# Script de instalação rápida para Linux/macOS
# Instala UV (se necessário) e dependências do ani-tupi

set -e

echo "🚀 Instalação rápida do ani-tupi"
echo "================================"

# Verifica se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado!"
    echo "   Instale Python 3.12+ primeiro:"
    echo "   - Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "   - Fedora: sudo dnf install python3 python3-pip"
    echo "   - macOS: brew install python@3.12"
    exit 1
fi

echo "✅ Python $(python3 --version) encontrado"

# Verifica se UV está instalado
if ! command -v uv &> /dev/null; then
    echo ""
    echo "📦 Instalando UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Adiciona UV ao PATH da sessão atual
    export PATH="$HOME/.cargo/bin:$PATH"

    echo "✅ UV instalado!"
else
    echo "✅ UV já está instalado"
fi

# Sincroniza dependências
echo ""
echo "📚 Instalando dependências..."
uv sync

echo ""
echo "✨ Dependências instaladas!"
echo ""

# Pergunta se quer instalar como CLI global
read -p "Deseja instalar como CLI global? (S/n): " install_global

if [[ ! "$install_global" =~ ^[Nn]$ ]]; then
    echo ""
    echo "📦 Instalando CLI global..."
    uv tool install .

    echo ""
    echo "✅ Instalação concluída!"
    echo ""
    echo "🎬 Use em qualquer lugar:"
    echo "   ani-tupi      # Assistir anime"
    echo "   manga-tupi    # Ler mangá"
    echo ""
    echo "💡 Se os comandos não funcionarem, adicione ao PATH:"
    echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    echo "   source ~/.bashrc"
else
    echo ""
    echo "✅ Instalação local concluída!"
    echo ""
    echo "💡 Como usar:"
    echo "   1. Rodar diretamente:"
    echo "      uv run ani-tupi"
    echo ""
    echo "   2. Buildar executável:"
    echo "      uv run build.py"
    echo ""
    echo "   3. Instalar CLI global depois:"
    echo "      uv tool install ."
fi

echo ""
echo "🎬 Aproveite! Bom anime!"
