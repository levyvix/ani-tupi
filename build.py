#!/usr/bin/env python3
"""
Script de build multiplataforma para ani-tupi
Usa UV para gerenciar dependências e PyInstaller para criar executável
"""

import subprocess
import sys
import shutil
import platform
from pathlib import Path


def run_command(cmd, check=True, shell=False):
    """Executa comando e mostra output"""
    print(f"\n🔧 Executando: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd,
        check=check,
        shell=shell,
        text=True,
        capture_output=False
    )
    return result.returncode == 0


def check_uv_installed():
    """Verifica se UV está instalado"""
    try:
        subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True
        )
        print("✅ UV já está instalado")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_uv():
    """Instala UV automaticamente"""
    print("\n📦 UV não encontrado. Instalando...")

    system = platform.system()

    if system in ["Linux", "Darwin"]:  # Linux ou macOS
        install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
        if run_command(install_cmd, shell=True, check=False):
            print("✅ UV instalado com sucesso!")
            # Adiciona UV ao PATH temporariamente
            home = Path.home()
            uv_bin = home / ".cargo" / "bin"
            if uv_bin.exists():
                import os
                os.environ["PATH"] = f"{uv_bin}:{os.environ['PATH']}"
            return True
    elif system == "Windows":
        install_cmd = "powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
        if run_command(install_cmd, shell=True, check=False):
            print("✅ UV instalado com sucesso!")
            return True

    print("❌ Falha ao instalar UV. Instale manualmente:")
    print("   Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh")
    print("   Windows: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"")
    return False


def sync_dependencies():
    """Sincroniza dependências usando UV"""
    print("\n📚 Sincronizando dependências...")
    return run_command(["uv", "sync", "--all-extras"])


def build_executable():
    """Cria executável usando PyInstaller"""
    print("\n🏗️  Buildando executável com PyInstaller...")

    # Descobre todos os plugins
    plugins_dir = Path("plugins")
    plugins = []

    if plugins_dir.exists():
        for plugin_file in plugins_dir.glob("*.py"):
            if plugin_file.name != "__init__.py":
                plugin_name = f"plugins.{plugin_file.stem}"
                plugins.append(plugin_name)

    # Monta comando do PyInstaller
    build_cmd = [
        "uv", "run",
        "pyinstaller",
        "--name", "ani-tupi",
        "--onefile",
        "main.py",
        "--add-data", f"plugins{':' if platform.system() != 'Windows' else ';'}plugins",
        "--hidden-import", "plugins",
    ]

    # Adiciona plugins como hidden imports
    for plugin in plugins:
        build_cmd.extend(["--hidden-import", plugin])

    if not run_command(build_cmd):
        return False

    # Copia plugins para dist
    print("\n📁 Copiando plugins para dist/")
    dist_plugins = Path("dist") / "plugins"

    if dist_plugins.exists():
        shutil.rmtree(dist_plugins)

    shutil.copytree(plugins_dir, dist_plugins)
    print("✅ Plugins copiados com sucesso!")

    return True


def main():
    """Função principal do build"""
    print("🚀 Iniciando build do ani-tupi...")
    print(f"🖥️  Sistema: {platform.system()} {platform.machine()}")
    print(f"🐍 Python: {sys.version}")

    # Verifica/instala UV
    if not check_uv_installed():
        if not install_uv():
            sys.exit(1)

    # Sincroniza dependências
    if not sync_dependencies():
        print("❌ Erro ao sincronizar dependências")
        sys.exit(1)

    # Build do executável
    if not build_executable():
        print("❌ Erro ao buildar executável")
        sys.exit(1)

    print("\n" + "="*60)
    print("✨ Build concluído com sucesso!")
    print("="*60)
    print(f"\n📦 Executável criado em: {Path('dist').absolute() / 'ani-tupi'}")
    print("\n💡 Para usar:")

    if platform.system() == "Windows":
        print("   - Adicione o diretório dist\\ ao PATH")
        print("   - Ou execute: .\\dist\\ani-tupi.exe")
    else:
        print("   - Execute: ./dist/ani-tupi")
        print("   - Ou adicione dist/ ao PATH")

    print("\n🎬 Aproveite! Bom anime!")


if __name__ == "__main__":
    main()
