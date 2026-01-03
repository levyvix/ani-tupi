#!/usr/bin/env python3
"""Instala ani-tupi como CLI global usando UV.

Execute com:
  uv run install-cli.py
  ou
  python install-cli.py
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# Fix encoding para Windows suportar emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def run_command(cmd, check=True, shell=False):
    """Executa comando e mostra output."""
    result = subprocess.run(cmd, check=check, text=True, shell=shell)
    return result.returncode == 0


def check_uv_installed() -> bool | None:
    """Verifica se UV está instalado."""
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_uv() -> bool:
    """Instala UV automaticamente usando pip."""
    # Tenta pip3 primeiro, depois pip
    pip_cmd = None
    for cmd in ["pip3", "pip"]:
        try:
            subprocess.run([cmd, "--version"], check=True, capture_output=True)
            pip_cmd = cmd
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not pip_cmd:
        return False

    # Instala UV via pip
    install_cmd = [pip_cmd, "install", "--user", "uv"]
    if run_command(install_cmd, check=False):
        # Adiciona scripts do Python ao PATH
        if platform.system() == "Windows":
            # Windows: Scripts vai para AppData\Roaming\Python\Python3X\Scripts
            python_version = f"Python{sys.version_info.major}{sys.version_info.minor}"
            scripts_dir = (
                Path.home() / "AppData" / "Roaming" / "Python" / python_version / "Scripts"
            )
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
            with open(os.environ.get("GITHUB_PATH"), "a") as f:  # type: ignore
                f.write(f"{scripts_dir}\n")

        return True

    return False


def install_as_cli() -> bool:
    """Instala ani-tupi como ferramenta CLI global."""
    # Instala usando uv tool install --reinstall (força rebuild mesmo se já instalado)
    if not run_command(["uv", "tool", "install", "--reinstall", "."], check=False):
        return False

    # Adiciona ao GITHUB_PATH se estiver no GitHub Actions
    if os.getenv("GITHUB_PATH"):
        tool_bin = Path.home() / ".local" / "bin"
        if platform.system() == "Windows":
            tool_bin = Path.home() / ".local" / "bin"  # UV tool bin no Windows

        with open(os.getenv("GITHUB_PATH"), "a") as f:
            f.write(f"{tool_bin}\n")

    return True


def show_path_info() -> None:
    """Mostra informações sobre o PATH."""
    system = platform.system()
    print("\n✅ ani-tupi instalado com sucesso como CLI global!")
    print("\nPróximos passos:")

    if system == "Windows":
        bin_path = Path.home() / ".local" / "bin"
        print(f"  • Adicione ao PATH: {bin_path}")
        print("  • Execute no terminal: ani-tupi")
    else:
        bin_path = Path.home() / ".local" / "bin"
        print(f"  • CLI disponível em: {bin_path}/ani-tupi")
        shell_rc = "~/.bashrc" if (Path.home() / ".bashrc").exists() else "~/.zshrc"
        print(f"  • Adicione ao {shell_rc}: export PATH=\"{bin_path}:$PATH\"")
        print("  • Execute: ani-tupi")


def main() -> None:
    # Verifica/instala UV
    if not check_uv_installed():
        print("UV não encontrado. Instalando...")
        if not install_uv():
            print("❌ Falha ao instalar UV", file=sys.stderr)
            sys.exit(1)

        # Verifica se instalação funcionou
        if not check_uv_installed():
            print("❌ UV ainda não está acessível após instalação", file=sys.stderr)
            sys.exit(1)
        print("✅ UV instalado com sucesso")

    # Instala CLI
    print("Instalando ani-tupi como CLI global...")
    if not install_as_cli():
        print("❌ Falha ao instalar ani-tupi", file=sys.stderr)
        sys.exit(1)

    # Mostra informações
    show_path_info()


if __name__ == "__main__":
    main()
