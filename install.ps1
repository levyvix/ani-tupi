# Script de instalação rápida para Windows (PowerShell)
# Instala UV (se necessário) e dependências do ani-tupi

$ErrorActionPreference = "Stop"

Write-Host "🚀 Instalação rápida do ani-tupi" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Verifica se Python está instalado
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion encontrado" -ForegroundColor Green
} catch {
    Write-Host "❌ Python 3 não encontrado!" -ForegroundColor Red
    Write-Host "   Instale Python 3.12+ primeiro:" -ForegroundColor Yellow
    Write-Host "   - https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "   - Ou via winget: winget install Python.Python.3.12" -ForegroundColor Yellow
    exit 1
}

# Verifica se UV está instalado
$uvInstalled = $false
try {
    $null = uv --version 2>&1
    $uvInstalled = $true
    Write-Host "✅ UV já está instalado" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "📦 Instalando UV..." -ForegroundColor Yellow

    try {
        Invoke-Expression "& { $(Invoke-RestMethod https://astral.sh/uv/install.ps1) }"

        # Adiciona UV ao PATH da sessão atual
        $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"

        Write-Host "✅ UV instalado!" -ForegroundColor Green
        $uvInstalled = $true
    } catch {
        Write-Host "❌ Erro ao instalar UV" -ForegroundColor Red
        Write-Host "   Tente instalar manualmente:" -ForegroundColor Yellow
        Write-Host "   powershell -c ""irm https://astral.sh/uv/install.ps1 | iex""" -ForegroundColor Yellow
        exit 1
    }
}

# Sincroniza dependências
Write-Host ""
Write-Host "📚 Instalando dependências..." -ForegroundColor Yellow
uv sync

Write-Host ""
Write-Host "✨ Dependências instaladas!" -ForegroundColor Green
Write-Host ""

# Pergunta se quer instalar como CLI global
$installGlobal = Read-Host "Deseja instalar como CLI global? (S/n)"

if ($installGlobal -notmatch "^[Nn]$") {
    Write-Host ""
    Write-Host "📦 Instalando CLI global..." -ForegroundColor Yellow
    uv tool install .

    Write-Host ""
    Write-Host "✅ Instalação concluída!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🎬 Use em qualquer lugar:" -ForegroundColor Cyan
    Write-Host "   ani-tupi      # Assistir anime"
    Write-Host "   manga-tupi    # Ler mangá"
    Write-Host ""
    Write-Host "💡 Se os comandos não funcionarem, verifique se está no PATH:" -ForegroundColor Yellow
    Write-Host "   $env:USERPROFILE\.local\bin"
} else {
    Write-Host ""
    Write-Host "✅ Instalação local concluída!" -ForegroundColor Green
    Write-Host ""
    Write-Host "💡 Como usar:" -ForegroundColor Cyan
    Write-Host "   1. Rodar diretamente:"
    Write-Host "      uv run ani-tupi"
    Write-Host ""
    Write-Host "   2. Buildar executável:"
    Write-Host "      uv run build.py"
    Write-Host ""
    Write-Host "   3. Instalar CLI global depois:"
    Write-Host "      uv tool install ."
}

Write-Host ""
Write-Host "🎬 Aproveite! Bom anime!" -ForegroundColor Cyan
