import importlib
import sys
from abc import ABC, abstractstaticmethod
from os.path import isfile, join, abspath, dirname
from os import listdir


class PluginInterface(ABC):
    @abstractstaticmethod
    def search_anime():
        raise NotImplementedError

    @abstractstaticmethod
    def search_episodes():
        raise NotImplementedError

    @abstractstaticmethod
    def search_player_src():
        raise NotImplementedError


def get_resource_path(relative_path):
    """Get the path to resources, whether running as script or executable."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller executable
        return join(sys._MEIPASS, relative_path)
    # Use directory where this file is located (works for both dev and installed)
    return join(dirname(abspath(__file__)), relative_path)


def load_plugins(languages: dict, plugins=None) -> None:
    path = get_resource_path("plugins/")
    system = {"__init__.py", "utils.py"}
    plugins = (
        plugins
        if plugins is not None
        else [
            file[:-3]
            for file in listdir(path)
            if isfile(join(path, file)) and file not in system
        ]
    )
    for plugin in plugins:
        plugin = importlib.import_module("plugins." + plugin)
        plugin.load(languages)
