#!/bin/bash
# Install best available image viewer for manga reading

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 INSTALADOR DE VISUALIZADOR DE IMAGENS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if already installed
check_viewer() {
    if command -v $1 &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Try to install eog first (best option)
echo "1️⃣  Tentando instalar EOG (Eye of GNOME)..."
if sudo apt update && sudo apt install -y eog; then
    echo "✓ EOG instalado com sucesso!"
    echo ""
    echo "Para usar com manga-tupi, basta rodar:"
    echo "  manga-tupi"
    echo ""
    echo "Controles:"
    echo "  → Próxima página"
    echo "  ← Página anterior"
    echo "  Esc Sair"
    exit 0
fi

echo ""
echo "2️⃣  EOG não disponível, tentando Nomacs..."
if sudo apt update && sudo apt install -y nomacs; then
    echo "✓ Nomacs instalado com sucesso!"
    echo ""
    echo "Para usar com manga-tupi:"
    echo "  export MANGA_VIEWER=nomacs"
    echo "  manga-tupi"
    exit 0
fi

echo ""
echo "3️⃣  Nomacs não disponível, tentando Geeqie..."
if sudo apt update && sudo apt install -y geeqie; then
    echo "✓ Geeqie instalado com sucesso!"
    echo ""
    echo "Para usar com manga-tupi:"
    echo "  export MANGA_VIEWER=geeqie"
    echo "  manga-tupi"
    exit 0
fi

echo ""
echo "❌ Não consegui instalar nenhum visualizador"
echo "Tente manualmente:"
echo "  sudo apt install eog"
echo "  sudo apt install nomacs"
echo "  sudo apt install geeqie"
