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
    """Instala UV automaticamente"""
    print("\n📦 UV não encontrado. Instalando...")
    system = platform.system()

    if system in ["Linux", "Darwin"]:  # Linux ou macOS
        install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
        if run_command(install_cmd, shell=True, check=False):
            print("✅ UV instalado com sucesso!")
            # Adiciona UV ao PATH da sessão atual
            home = Path.home()
            uv_bin = home / ".cargo" / "bin"
            if uv_bin.exists():
                os.environ["PATH"] = f"{uv_bin}:{os.environ['PATH']}"
            return True
    elif system == "Windows":
        # Usar Python puro para evitar problemas com PowerShell em CI
        import urllib.request
        import tempfile

        try:
            print("🔧 Baixando instalador do UV...")
            installer_url = "https://astral.sh/uv/install.ps1"

            # Baixa o instalador
            with urllib.request.urlopen(installer_url) as response:
                installer_script = response.read().decode('utf-8')

            # Salva temporariamente
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False) as f:
                f.write(installer_script)
                script_path = f.name

            # Executa com PowerShell diretamente (sem -c)
            install_cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-File', script_path]

            if run_command(install_cmd, check=False):
                print("✅ UV instalado com sucesso!")
                # Adiciona UV ao PATH da sessão atual
                home = Path.home()
                uv_bin = home / ".cargo" / "bin"
                if uv_bin.exists():
                    os.environ["PATH"] = f"{uv_bin};{os.environ['PATH']}"

                # Remove arquivo temporário
                try:
                    os.unlink(script_path)
                except:
                    pass

                return True

            # Limpa em caso de erro
            try:
                os.unlink(script_path)
            except:
                pass

        except Exception as e:
            print(f"❌ Erro ao instalar UV: {e}")

    print("❌ Falha ao instalar UV automaticamente.")
    print("\n📦 Instale manualmente:")
    print("   Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh")
    print("   Windows: irm https://astral.sh/uv/install.ps1 | iex")
    return False


def install_as_cli():
    """Instala ani-tupi como ferramenta CLI global"""
    print("🚀 Instalando ani-tupi como CLI global...")
    print("=" * 60)

    # Instala usando uv tool install
    if not run_command(["uv", "tool", "install", "."]):
        print("\n❌ Erro ao instalar CLI")
        return False

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
