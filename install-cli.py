#!/usr/bin/env python3
"""Instala ani-tupi como CLI global usando UV
Execute com: python install-cli.py.
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
    cmd if isinstance(cmd, str) else " ".join(cmd)
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

        return True

    return False


def install_as_cli() -> bool:
    """Instala ani-tupi como ferramenta CLI global."""
    # Instala usando uv tool install --reinstall (força rebuild mesmo se já instalado)
    if not run_command(["uv", "tool", "install", "--reinstall", "."]):
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


    if system == "Windows":
        Path.home() / ".cargo" / "bin"
    else:
        Path.home() / ".local" / "bin"

        "~/.bashrc" if Path.home() / ".bashrc" else "~/.zshrc"



def main() -> None:

    # Verifica/instala UV
    if not check_uv_installed():
        if not install_uv():
            sys.exit(1)

        # Verifica se instalação funcionou
        if not check_uv_installed():
            sys.exit(1)
    else:
        pass

    # Instala CLI
    if not install_as_cli():
        sys.exit(1)

    # Mostra informações
    show_path_info()


if __name__ == "__main__":
    main()
