import click
import os
import json
import yt_dlp
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from concurrent.futures import ThreadPoolExecutor

CREDENTIALS_FILE = "credentials.json"
DOWNLOADED_VIDEOS_DIR = "downloaded_videos"


def get_webdriver(isHeadless=False):
    options = webdriver.ChromeOptions()

    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.96 "
        "Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if isHeadless:
        options.add_argument("--headless")

    driver = webdriver.Chrome(options=options)

    driver.get("https://www.patreon.com/home")

    return driver


def get_credentials():
    driver = get_webdriver()

    driver.get("https://www.patreon.com/login")
    WebDriverWait(driver, 9999).until(
        lambda d: d.current_url == "https://www.patreon.com/home"
    )

    with open(CREDENTIALS_FILE, "w") as f:
        cookies = driver.get_cookies()
        local_storage = driver.execute_script("return window.localStorage;")
        keys_to_remove = [
            "clear",
            "length",
            "key",
            "getItem",
            "setItem",
            "removeItem"
        ]

        for key in keys_to_remove:
            del local_storage[key]

        json_contents = {
            "cookies": cookies,
            "local_storage": local_storage
        }

        json.dump(json_contents, f, indent=2)


def load_credentials(driver):
    with open(CREDENTIALS_FILE, "r") as f:
        credentials = json.load(f)

        for cookie in credentials["cookies"]:
            driver.add_cookie(cookie)

        driver.execute_script("window.localStorage.clear();")

        for key, value in credentials["local_storage"].items():
            driver.execute_script(
                f"window.localStorage.setItem('{key}', '{value}');"
            )

        driver.get("https://www.patreon.com/home")

        return driver


def get_webdriver_with_credentials(isHeadless=False):
    driver = get_webdriver(isHeadless)

    load_credentials(driver)

    return driver


def wait_for_filter_apply(driver, target_url):
    WebDriverWait(driver, 9999).until(
        lambda d: d.current_url == target_url
    )

    filter_dialog_selector = '[data-tag="dialog-footer"]'

    WebDriverWait(driver, 9999).until(
        lambda d: d.execute_script(
            f"return !!document.querySelector('{filter_dialog_selector}');"
        )
    )

    filter_apply_button_selector = '[data-tag="dialog-action-primary"]'

    driver.execute_script(f"""
        const button =
            document.querySelector('{filter_apply_button_selector}');

        if (button) {{
            button.addEventListener('click', function() {{
                window.filterClicked = true;
            }});
        }}
    """)

    WebDriverWait(driver, 9999).until(
        lambda d: d.execute_script("return window.filterClicked;")
    )

    print("Filter applied")


def get_video_list(driver):
    video_items = []
    video_list = []

    while True:
        try:
            button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//div[contains(text(), "더 보기")]'
                ))
            )

            button.click()
        except TimeoutException:
            print("TimeoutException")
            break
        except NoSuchElementException:
            print("NoSuchElementException")
            break
        except Exception as e:
            print(e)
            break

    post_cards = driver.find_elements(
        By.CSS_SELECTOR,
        'div[data-tag="post-card"]'
    )

    for post_card in post_cards:
        post_title = post_card.find_element(
            By.CSS_SELECTOR,
            'span[data-tag="post-title"]'
        ).text
        post_url = post_card.find_element(
            By.CSS_SELECTOR,
            'span[data-tag="post-title"] a'
        ).get_attribute("href")

        video_items.append({
            "title": post_title,
            "url": post_url
        })

    for video_item in video_items:
        try:
            driver.get(video_item["url"])

            WebDriverWait(driver, 10).until(
                lambda d: d.find_element(
                    By.CSS_SELECTOR,
                    'iframe'
                )
            )

            video_embed_url = driver.find_element(
                By.CSS_SELECTOR,
                'iframe'
            ).get_attribute("src")

            video_list.append({
                "title": video_item["title"],
                "url": video_embed_url,
                "post_url": post_url
            })
        except Exception as e:
            print(e)
            pass

    return video_list


def download_video(video):
    with yt_dlp.YoutubeDL({
        "outtmpl": f"{DOWNLOADED_VIDEOS_DIR}/{video['title']}.%(ext)s"
    }) as ydl:
        ydl.download([video["url"]])


def download_videos(video_list):
    if not os.path.exists(DOWNLOADED_VIDEOS_DIR):
        os.makedirs(DOWNLOADED_VIDEOS_DIR)

    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(download_video, video_list)


@click.command()
def main():
    if not os.path.exists(CREDENTIALS_FILE):
        if click.confirm(
            "Patreon account information cannot be verified. "
            "Would you like to login?"
        ):
            get_credentials()
        else:
            return

    target_url = click.prompt(
        "Please enter the URL of the Patreon profile you want to download "
        "ex) https://www.patreon.com/c/username/posts"
    )
    filter_apply = click.confirm(
        "Would you like to apply a list filter before downloading?"
    )

    if filter_apply:
        click.echo(
            "When the post page is displayed, "
            "select the filter to be applied when downloading and click the "
            "Apply Filter button."
        )

    driver = get_webdriver_with_credentials(isHeadless=not filter_apply)

    driver.get(target_url)

    if filter_apply:
        wait_for_filter_apply(driver, target_url)

    video_list = get_video_list(driver)

    download_videos(video_list)

    driver.quit()

    click.echo(
        "Download completed, "
        "videos are saved in the downloaded_videos directory."
    )


if __name__ == "__main__":
    main()
