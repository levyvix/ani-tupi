#!/usr/bin/env python3
"""
Instala ani-tupi como CLI global usando UV
Execute com: python install-cli.py
"""

import subprocess
import sys
import platform
import os
from pathlib import Path

# Fix encoding para Windows suportar emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def run_command(cmd, check=True, shell=False):
    """Executa comando e mostra output"""
    cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
    print(f"\n🔧 Executando: {cmd_str}")
    result = subprocess.run(cmd, check=check, text=True, shell=shell)
    return result.returncode == 0


def check_uv_installed():
    """Verifica se UV está instalado"""
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_uv():
    """Instala UV automaticamente usando pip"""
    print("\n📦 UV não encontrado. Instalando via pip...")

    # Tenta pip3 primeiro, depois pip
    pip_cmd = None
    for cmd in ['pip3', 'pip']:
        try:
            subprocess.run([cmd, '--version'], check=True, capture_output=True)
            pip_cmd = cmd
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not pip_cmd:
        print("❌ pip não encontrado!")
        print("\n📦 Instale pip primeiro e tente novamente")
        return False

    # Instala UV via pip
    install_cmd = [pip_cmd, 'install', '--user', 'uv']
    if run_command(install_cmd, check=False):
        print("✅ UV instalado com sucesso!")

        # Adiciona scripts do Python ao PATH
        if platform.system() == "Windows":
            # Windows: Scripts vai para AppData\Roaming\Python\Python3X\Scripts
            python_version = f"Python{sys.version_info.major}{sys.version_info.minor}"
            scripts_dir = Path.home() / "AppData" / "Roaming" / "Python" / python_version / "Scripts"
            if scripts_dir.exists():
                os.environ["PATH"] = f"{scripts_dir};{os.environ['PATH']}"
        elif platform.system() == "Darwin":
            # macOS: Scripts vai para ~/Library/Python/X.Y/bin
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            scripts_dir = Path.home() / "Library" / "Python" / python_version / "bin"
            if scripts_dir.exists():
                os.environ["PATH"] = f"{scripts_dir}:{os.environ['PATH']}"
        else:
            # Linux: Scripts vai para ~/.local/bin
            scripts_dir = Path.home() / ".local" / "bin"
            if scripts_dir.exists():
                os.environ["PATH"] = f"{scripts_dir}:{os.environ['PATH']}"

        # Se estiver no GitHub Actions, adiciona ao GITHUB_PATH
        if os.getenv("GITHUB_PATH"):
            with open(os.getenv("GITHUB_PATH"), "a") as f:
                f.write(f"{scripts_dir}\n")
            print(f"✅ Adicionado {scripts_dir} ao GITHUB_PATH")

        return True

    print("❌ Falha ao instalar UV.")
    print("\n📦 Tente instalar manualmente:")
    print(f"   {pip_cmd} install uv")
    return False


def install_as_cli():
    """Instala ani-tupi como ferramenta CLI global"""
    print("🚀 Instalando ani-tupi como CLI global...")
    print("=" * 60)

    # Instala usando uv tool install
    if not run_command(["uv", "tool", "install", "."]):
        print("\n❌ Erro ao instalar CLI")
        return False

    # Adiciona ao GITHUB_PATH se estiver no GitHub Actions
    if os.getenv("GITHUB_PATH"):
        tool_bin = Path.home() / ".local" / "bin"
        if platform.system() == "Windows":
            tool_bin = Path.home() / ".local" / "bin"  # UV tool bin no Windows

        with open(os.getenv("GITHUB_PATH"), "a") as f:
            f.write(f"{tool_bin}\n")
        print(f"✅ Adicionado {tool_bin} ao GITHUB_PATH")

    return True


def show_path_info():
    """Mostra informações sobre o PATH"""
    system = platform.system()

    print("\n" + "=" * 60)
    print("✨ CLI instalado com sucesso!")
    print("=" * 60)

    if system == "Windows":
        uv_bin = Path.home() / ".cargo" / "bin"
        print(f"\n📁 Comandos instalados em: {uv_bin}")
        print("\n💡 Certifique-se de que este diretório está no PATH:")
        print(f"   {uv_bin}")
        print("\n   Para adicionar permanentemente:")
        print("   1. Abra 'Variáveis de Ambiente'")
        print("   2. Adicione o caminho acima ao PATH")
        print("   3. Reinicie o terminal")
    else:
        uv_bin = Path.home() / ".local" / "bin"
        print(f"\n📁 Comandos instalados em: {uv_bin}")
        print("\n💡 Adicione ao PATH se ainda não estiver:")

        shell_rc = "~/.bashrc" if Path.home() / ".bashrc" else "~/.zshrc"
        print(f"\n   echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> {shell_rc}")
        print(f"   source {shell_rc}")

    print("\n🎬 Comandos disponíveis:")
    print("   ani-tupi  \t - Assistir anime")
    print("     ani-tupi --continue-watching \t - Continuar assistindo")
    print("   manga-tupi    - Ler mangá")
    print("\n✅ Pronto! Execute 'ani-tupi' em qualquer lugar!")


def main():
    print("🎬 Instalador CLI do ani-tupi")
    print("=" * 60)
    print(f"🐍 Python: {sys.version.split()[0]}")
    print(f"🖥️  Sistema: {platform.system()}")

    # Verifica/instala UV
    if not check_uv_installed():
        print("\n⚠️  UV não está instalado")
        if not install_uv():
            sys.exit(1)

        # Verifica se instalação funcionou
        if not check_uv_installed():
            print("\n❌ UV foi instalado mas não está disponível no PATH")
            print("Reinicie o terminal e execute novamente:")
            print("   python install-cli.py")
            sys.exit(1)
    else:
        print("✅ UV já está instalado")

    # Instala CLI
    if not install_as_cli():
        sys.exit(1)

    # Mostra informações
    show_path_info()


if __name__ == "__main__":
    main()
