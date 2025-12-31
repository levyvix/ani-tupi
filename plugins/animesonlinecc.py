from multiprocessing.pool import ThreadPool
from os import cpu_count

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from loader import PluginInterface
from repository import rep

from .utils import is_firefox_installed_as_snap


class AnimesOnlineCC(PluginInterface):
    languages = ["pt-br"]
    name = "animesonlinecc"

    @staticmethod
    def search_anime(query) -> None:
        url = "https://animesonlinecc.to/search/" + "+".join(query.split())
        html_content = requests.get(url)
        soup = BeautifulSoup(html_content.text, "html.parser")
        divs = soup.find_all("div", class_="data")
        titles_urls = [div.h3.a["href"] for div in divs]
        titles = [div.h3.a.get_text() for div in divs]
        for title, url in zip(titles, titles_urls, strict=False):
            rep.add_anime(title, url, AnimesOnlineCC.name)

        def parse_seasons(title, url) -> None:
            html = requests.get(url)
            soup = BeautifulSoup(html.text, "html.parser")
            num_seasons = len(list(soup.find_all("div", class_="se-c")))
            if num_seasons > 1:
                for n in range(2, num_seasons + 1):
                    rep.add_anime(
                        title + " Season " + str(n), url, AnimesOnlineCC.name, n
                    )

        with ThreadPool(cpu_count()) as pool:
            for title, url in zip(titles, titles_urls, strict=False):
                pool.apply(parse_seasons, args=(title, url))

    @staticmethod
    def search_episodes(anime, url, season) -> None:
        html_episodes_page = requests.get(url)
        soup = BeautifulSoup(html_episodes_page.text, "html.parser")
        seasons = list(soup.find_all("ul", class_="episodios"))
        season = seasons[season - 1 if season is not None else 0]
        urls, titles = [], []
        for div in season.find_all("div", class_="episodiotitle"):
            urls.append(div.a["href"])
            titles.append(div.a.get_text())
        rep.add_episode_list(anime, titles, urls, AnimesOnlineCC.name)

    @staticmethod
    def search_player_src(url_episode, container, event) -> None:
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")

        try:
            if is_firefox_installed_as_snap():
                service = webdriver.FirefoxService(
                    executable_path="/snap/bin/geckodriver"
                )
                driver = webdriver.Firefox(options=options, service=service)
            else:
                driver = webdriver.Firefox(options=options)
        except:
            msg = "Firefox not installed."
            raise Exception(msg)

        driver.get(url_episode)

        try:
            class_ = (
                "/html/body/div[1]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/iframe"
            )
            params = (By.XPATH, class_)
            WebDriverWait(driver, 7).until(
                EC.visibility_of_all_elements_located(params)
            )
        except:
            driver.quit()
            msg = "nor iframe nor video tags were found in animesonlinecc."
            raise Exception(msg)

        product = driver.find_element(params[0], params[1])
        link = product.get_property("src")
        driver.quit()

        if not event.is_set():
            container.append(link)
            event.set()


def load(languages_dict) -> None:
    can_load = False
    for language in AnimesOnlineCC.languages:
        if language in languages_dict:
            can_load = True
            break
    if not can_load:
        return
    rep.register(AnimesOnlineCC)
