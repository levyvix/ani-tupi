import importlib
import sys
from abc import ABC, abstractstaticmethod
from os.path import isfile, join, abspath
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
        return join(sys._MEIPASS, relative_path)
    return join(abspath("."), relative_path)


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
