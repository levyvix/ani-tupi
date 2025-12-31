import requests
from bs4 import BeautifulSoup
from repository import rep
from loader import PluginInterface
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .utils import is_firefox_installed_as_snap


class AnimeFire(PluginInterface):
    languages = ["pt-br"]
    name = "animefire"

    @staticmethod
    def search_anime(query):
        url = "https://animefire.plus/pesquisar/" + "-".join(query.split())
        html_content = requests.get(url)
        soup = BeautifulSoup(html_content.text, "html.parser")
        target_class = (
            "col-6 col-sm-4 col-md-3 col-lg-2 mb-1 minWDanime divCardUltimosEps"
        )
        titles_urls = [
            div.article.a["href"]
            for div in soup.find_all("div", class_=target_class)
            if "title" in div.attrs
        ]
        titles = [h3.get_text() for h3 in soup.find_all("h3", class_="animeTitle")]
        for title, url in zip(titles, titles_urls):
            rep.add_anime(title, url, AnimeFire.name)

    @staticmethod
    def search_episodes(anime, url, params):
        html_episodes_page = requests.get(url)
        soup = BeautifulSoup(html_episodes_page.text, "html.parser")
        episode_links = [
            a["href"]
            for a in soup.find_all(
                "a", class_="lEp epT divNumEp smallbox px-2 mx-1 text-left d-flex"
            )
        ]
        opts = [
            a.get_text()
            for a in soup.find_all(
                "a", class_="lEp epT divNumEp smallbox px-2 mx-1 text-left d-flex"
            )
        ]
        rep.add_episode_list(anime, opts, episode_links, AnimeFire.name)

    @staticmethod
    def search_player_src(url_episode, container, event):
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
            raise Exception("Firefox not installed.")

        driver.get(url_episode)
        try:
            params = (By.ID, "my-video_html5_api")
            element = WebDriverWait(driver, 7).until(
                EC.visibility_of_all_elements_located(params)
            )
        except:
            try:
                xpath = "/html/body/div[2]/div[2]/div/div[1]/div[1]/div/div/div[2]/div[4]/iframe"
                params = (By.XPATH, xpath)
                element = WebDriverWait(driver, 7).until(
                    EC.visibility_of_all_elements_located(params)
                )
            except:
                driver.quit()
                raise Exception("nor iframe nor video tags were found in animefire.")

        product = driver.find_element(params[0], params[1])
        link = product.get_property("src")
        driver.quit()

        if not event.is_set():
            container.append(link)
            event.set()


def load(languages_dict):
    can_load = False
    for language in AnimeFire.languages:
        if language in languages_dict:
            can_load = True
            break
    if not can_load:
        return
    rep.register(AnimeFire)
