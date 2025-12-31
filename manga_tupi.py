import os
import subprocess
import threading
from collections import defaultdict
from pathlib import Path
from sys import exit

import requests
from tqdm import tqdm

from menu import menu

base_url = "https://api.mangadex.org"

def run(dir_path) -> None:
    subprocess.run(["feh", dir_path, "-R 1", "--fullscreen", "--scale-down"], check=False)

def main() -> None:
    res = requests.get(
                f"{base_url}/manga",
                params={"title": input("Pesquise mangá: ")}).json()["data"]

    titles = []
    for manga in res:
        if "pt-br" not in manga["attributes"]["altTitles"]:
            try:
                titles.append(manga["attributes"]["title"]["en"])
            except:
                try:
                    titles.append(manga["attributes"]["title"]["ja"])
                except:
                    continue
        else:
            titles.append(manga["attributes"]["altTitles"]["pt-br"])

    title_ids = [manga["id"] for manga in res]
    selected_title = menu(titles)

    offset = 0
    def get(query):
        return requests.get(f"{base_url}/manga/{title_ids[titles.index(selected_title)]}/feed?{query}").json()["data"]
    current, chapters = [], []
    while not current or len(current) == 500:
        query = "&".join(["limit=500",
                      "translatedLanguage[]=pt-br",
                      "translatedLanguage[]=en",
                      "order[chapter]=asc",
                      "includeEmptyPages=0",
                      "includeFuturePublishAt=0",
                      f"offset={offset}"])
        current = get(query)
        chapters.extend(current)
        offset += 500
    chapter_sources = defaultdict(list)
    for chap in chapters:
        if chap["attributes"]["chapter"] is None:
            continue
        chapter_sources[chap["attributes"]["chapter"]].append(chap)
    chapters_num = [f"{chap:.0f}" if chap == int(chap) else f"{chap:.2f}" for chap in sorted(map(float, chapter_sources.keys()))]

    def chapter_selection(selected_chapter = None):
        nonlocal chapters_num, chapter_sources
        if not selected_chapter:
            selected_chapter = menu(chapters_num)
        else:
            try:
                selected_chapter = chapters_num[chapters_num.index(selected_chapter) + 1]
            except IndexError:
                exit()

        def select_language() -> None:
            nonlocal selected_chapter
            chapter_translates = [chap["attributes"]["translatedLanguage"] + " " + str(i + 1) for i, chap in enumerate(chapter_sources[selected_chapter])]
            chapter_ids = [chap["id"] for chap in chapter_sources[selected_chapter]]
            selected_opt = menu(chapter_translates)

            pages = requests.get(f"{base_url}/at-home/server/{chapter_ids[chapter_translates.index(selected_opt)]}").json()
            home = Path.home().as_posix() if os.name != "nt" else home.as_uri()
            dirs = [home, "Downloads", selected_title, selected_chapter]
            dir_path = Path("/".join(dirs) if os.name != "nt" else "\\".join(dirs))
            dir_path.mkdir(parents=True, exist_ok=True)
            first = True
            thread = threading.Thread(target=run, args=(dir_path,))

            for i in tqdm(range(len(pages["chapter"]["data"]))):
                url = pages["baseUrl"] + "/data/" + pages["chapter"]["hash"] + "/" + pages["chapter"]["data"][i]
                img_path = Path(str(dir_path) + f"/{i}.png")
                if not img_path.is_file():
                    img_data = requests.get(url).content
                    with img_path.open("wb") as img:
                        img.write(img_data)
                if first:
                    thread.start()
                    first = False
            if not first:
                thread.join()
        select_language()

        return selected_chapter

    prev = chapter_selection()
    while True:
        opt = menu(["Próximo"])
        if opt == "Próximo":
            prev = chapter_selection(prev)
        else:
            break



if __name__=="__main__":
    main()


