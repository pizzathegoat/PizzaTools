import os
import re
import sys
from playwright.sync_api import sync_playwright

BLUE = "\033[94m"
RESET = "\033[0m"

banner = f"""{BLUE}
  ____        _ _              _____ _
 / __ \\      | (_)            |  ___(_)
| |  | |_ __ | |_ _ __   ___  | |_   ___  __
| |  | | '_ \\| | | '_ \\ / _ \\ |  _| | \\ \\/ /
| |__| | | | | | | | | |  __/ | |   | |>  <
 \\____/|_| |_|_|_|_| |_|\\___| \\_|   |_/_/\\_\\

 [*] Online-Fix Downloader
 [*] Made by pizzathegoat_
{RESET}"""

def convert_numbers_to_roman(text):
    roman_map = {
        '1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V',
        '6': 'VI', '7': 'VII', '8': 'VIII', '9': 'IX', '10': 'X'
    }
    result = text
    for num, roman in roman_map.items():
        result = re.sub(rf'\b{num}\b', roman, result)
    return result

def normalize_text(text):
    text = re.sub(r'[\:\-\–\—\.\,\/\|\(\)\[\]]', ' ', text.lower())
    return ' '.join(text.split())

def find_download_button(page):
    strategies = [
        lambda: page.locator("a:has-text('DOWNLOAD')").first,
        lambda: page.locator("a:has-text('Download')").first,
        lambda: page.locator("a:has-text('download')").first,
        lambda: page.locator("a.download").first,
        lambda: page.locator("a.download-btn").first,
        lambda: page.locator("a.download-button").first,
        lambda: page.locator("button:has-text('DOWNLOAD')").first,
        lambda: page.locator("button:has-text('Download')").first,
        lambda: page.locator("text=DOWNLOAD").first,
        lambda: page.locator("text=Download").first,
        lambda: page.locator("a[href*='download']").first,
        lambda: page.locator("a[href*='Download']").first,
        lambda: page.locator("[role='button']:has-text('Download')").first,
        lambda: page.locator("[type='button']:has-text('Download')").first,
        lambda: page.locator("*:has-text('Download')").first,
    ]

    for strategy in strategies:
        try:
            element = strategy()
            if element.count() > 0 and element.is_visible():
                return element
        except:
            continue

    return None

def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    os.system("cls" if os.name == "nt" else "clear")
    print(banner)

    downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")

    stealth_script = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['de-DE', 'de', 'en-US', 'en']});
    """

    with sync_playwright() as p:
        print(f"{BLUE}[+] Starting headless browser in background...{RESET}")
        launch_options = {
            "headless": True,
            "args": [
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ],
        }
        chrome_roots = (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        )
        has_system_chrome = any(
            root and os.path.isfile(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
            for root in chrome_roots
        )
        if has_system_chrome:
            try:
                browser = p.chromium.launch(channel="chrome", **launch_options)
            except Exception as error:
                print(f"[!] Could not launch installed Chrome: {error}")
                browser = p.chromium.launch(**launch_options)
        else:
            browser = p.chromium.launch(**launch_options)

        context = browser.new_context(
            java_script_enabled=False,
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        page = context.new_page()

        while True:
            print(f"\n{BLUE}{'='*60}{RESET}")
            game = input(f"{BLUE}[>] Enter game name (or press ENTER to exit): {RESET}").strip()

            if not game:
                print(f"\n{BLUE}[+] Exiting program... {RESET}")
                break

            print(f"\n[+] Target: {game}")
            print("[+] Navigating to online-fix.me...")

            try:
                page.goto("https://online-fix.me", wait_until="commit")
                page.wait_for_timeout(1500)

                print("[+] Searching for game...")
                search = page.locator("#story")
                search.wait_for(state="visible", timeout=10000)
                search.click(force=True)
                search.fill(game, force=True)
                search.press("Enter")

                page.wait_for_timeout(2000)

                def try_find_game(search_lower):
                    all_links = page.locator("a")
                    link_count = all_links.count()

                    norm_search = normalize_text(search_lower)

                    for i in range(link_count):
                        try:
                            text = all_links.nth(i).text_content()
                            if text and ("по сети" in text.lower() or "online" in text.lower()):
                                text_clean = text.lower()
                                for suffix in [" по сети", " online"]:
                                    text_clean = text_clean.replace(suffix, "")
                                text_clean = text_clean.strip()
                                norm_text = normalize_text(text_clean)

                                if norm_text == norm_search:
                                    return all_links.nth(i), text.strip()
                        except:
                            continue

                    for i in range(link_count):
                        try:
                            text = all_links.nth(i).text_content()
                            if text and ("по сети" in text.lower() or "online" in text.lower()):
                                text_clean = text.lower()
                                for suffix in [" по сети", " online"]:
                                    text_clean = text_clean.replace(suffix, "")
                                text_clean = text_clean.strip()
                                norm_text = normalize_text(text_clean)

                                if norm_text.startswith(norm_search + " "):
                                    return all_links.nth(i), text.strip()
                        except:
                            continue

                    return None, None

                game_lower = game.lower().strip()
                game_roman = convert_numbers_to_roman(game)
                roman_lower = game_roman.lower().strip()

                target_link, match_text = try_find_game(game_lower)
                if not target_link and game_roman != game:
                    target_link, match_text = try_find_game(roman_lower)

                if not target_link:
                    search_box = page.locator("#story, input[name='story']").first
                    if game_roman != game:
                        page.wait_for_timeout(3000)
                        search_box.click(force=True)
                        search_box.fill("", force=True)
                        search_box.fill(game_roman, force=True)
                        search_box.press("Enter")
                        page.wait_for_timeout(2000)

                        target_link, match_text = try_find_game(roman_lower)

                if not target_link:
                    words = game.split()
                    if len(words) >= 2:
                        base_search = words[0]
                        page.wait_for_timeout(3000)
                        search_box = page.locator("#story, input[name='story']").first
                        search_box.click(force=True)
                        search_box.fill("", force=True)
                        search_box.fill(base_search, force=True)
                        search_box.press("Enter")
                        page.wait_for_timeout(2000)

                        target_link, match_text = try_find_game(game_lower)
                        if not target_link:
                            target_link, match_text = try_find_game(roman_lower)

                if not target_link:
                    print(f"[!] Could not find the game '{game}'.")
                    continue

                print(f"[+] Found: {match_text}")

                target_href = target_link.get_attribute("href")
                if target_href:
                    if not target_href.startswith("http"):
                        target_href = "https://online-fix.me" + target_href
                    page.goto(target_href, wait_until="domcontentloaded")
                else:
                    target_link.scroll_into_view_if_needed()
                    target_link.click(force=True)
                    page.wait_for_load_state("domcontentloaded")

                page.wait_for_timeout(1000)
                page.keyboard.press("End")
                page.wait_for_timeout(500)

                red_button = None
                button_strategies = [
                    lambda: page.locator("a:has-text('Скачать фикс с сервера')").first,
                    lambda: page.locator("a[href*='uploads.online-fix.me']").first,
                    lambda: page.locator("a:has-text('Скачать с Online-Fix Hosters')").first,
                    lambda: page.locator("a[href*='hosters.online-fix.me']").first,
                    lambda: page.locator("a:has-text('Скачать фикс')").first,
                    lambda: page.locator("a:has-text('Скачать')").first,
                ]

                for strat in button_strategies:
                    try:
                        btn = strat()
                        if btn.count() > 0 and btn.is_visible():
                            red_button = btn
                            print(f"[+] Selected: {btn.text_content().strip()}")
                            break
                    except:
                        continue

                if not red_button:
                    red_button = page.locator("a:has-text('Скачать фикс с сервера'), a:has-text('Скачать с Online-Fix Hosters'), a:has-text('Скачать')").first
                    red_button.wait_for(state="visible", timeout=15000)

                print("[+] Clicking download button...")
                with context.expect_page() as page_info:
                    red_button.click(force=True)

                new_page = page_info.value
                new_page.wait_for_load_state("commit")
                new_page.wait_for_timeout(3000)

                current_url = new_page.url
                print(f"[+] URL: {current_url}")

                if "hosters.online-fix.me" in current_url:
                    print("[+] Hoster page detected")
                    new_page.wait_for_timeout(3000)

                    try:
                        fd_tab = new_page.locator("text='FileDitch'").first
                        if fd_tab.count() > 0 and fd_tab.is_visible():
                            fd_tab.click(force=True)
                            new_page.wait_for_timeout(1500)
                    except:
                        pass

                    dl_buttons = new_page.locator("a:has-text('DOWNLOAD'), a:has-text('Download')")

                    if dl_buttons.count() > 0:
                        download_url = dl_buttons.first.get_attribute("href")
                        print(f"[+] Found download link: {download_url}")

                        print("[+] Opening external hoster...")
                        fd_context = browser.new_context(
                            java_script_enabled=True,
                            accept_downloads=True,
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            extra_http_headers={
                                "Accept-Language": "en-US,en;q=0.9",
                                "Sec-Ch-Ua": '"Chromium";v="120", "Not;A=Brand";v="24", "Google Chrome";v="120"',
                                "Sec-Ch-Ua-Mobile": "?0",
                                "Sec-Ch-Ua-Platform": '"Windows"'
                            }
                        )
                        fd_context.add_init_script(stealth_script)

                        fd_page = fd_context.new_page()

                        active_download = None
                        def handle_download(d):
                            nonlocal active_download
                            active_download = d

                        fd_page.on("download", handle_download)

                        print("[+] Waiting for Cloudflare verification (up to 30 seconds)...")
                        try:
                            fd_page.goto(download_url, wait_until="domcontentloaded", timeout=30000)
                        except:
                            pass

                        for _ in range(30):
                            if active_download:
                                break
                            fd_page.wait_for_timeout(1000)

                        if active_download:
                            final_path = os.path.join(downloads_path, active_download.suggested_filename)
                            print(f"[+] Auto-download triggered (Bypassed CF): {active_download.suggested_filename}")
                            active_download.save_as(final_path)
                            print(f"[+] Saved successfully to: {final_path}")
                        else:
                            print("[+] Searching for download button on hoster...")
                            download_btn = find_download_button(fd_page)

                            if download_btn:
                                print("[+] Starting download...")
                                with fd_page.expect_download(timeout=120000) as download_info:
                                    download_btn.click(force=True)

                                download = download_info.value
                                final_path = os.path.join(downloads_path, download.suggested_filename)
                                print(f"[+] Download: {download.suggested_filename}")
                                download.save_as(final_path)
                                print(f"[+] Saved successfully to: {final_path}")
                            else:
                                print("[!] No download button found and no auto-download triggered.")

                        fd_page.wait_for_timeout(3000)
                        fd_context.close()
                    else:
                        print("[!] No download button found on hoster page.")

                    new_page.close()

                elif "uploads.online-fix.me" in current_url:
                    print("[+] Server directory detected")
                    new_page.wait_for_timeout(2000)

                    fix_folder = None
                    try:
                        fix_folder = new_page.locator("a:has-text('Fix Repair'), a[href*='Fix_Repair']").first
                        if fix_folder.count() > 0:
                            print(f"[+] Found folder: {fix_folder.text_content().strip()}")
                            print("[+] Navigating into folder...")
                            fix_folder.click(force=True)
                            new_page.wait_for_load_state("domcontentloaded")
                            new_page.wait_for_timeout(3000)
                    except:
                        print("[*] No Fix Repair folder found, checking root directory...")

                    archive_link = None
                    all_links = new_page.locator("a")
                    link_count = all_links.count()

                    for i in range(link_count):
                        try:
                            href = all_links.nth(i).get_attribute("href") or ""
                            if href.lower().endswith(('.rar', '.7z', '.zip')):
                                archive_link = all_links.nth(i)
                                print(f"[+] Found archive file: {href}")
                                break
                        except:
                            continue

                    if archive_link is not None:
                        filename = archive_link.text_content().strip()
                        print(f"[+] Starting direct download: {filename}")

                        try:
                            with new_page.expect_download(timeout=120000) as download_info:
                                archive_link.click(force=True)

                            download = download_info.value
                            final_path = os.path.join(downloads_path, download.suggested_filename)
                            print(f"[+] Download active: {download.suggested_filename}")
                            download.save_as(final_path)
                            print(f"[+] Saved successfully to: {final_path}")
                        except Exception as e:
                            print(f"[!] Download failed: {e}")
                    else:
                        print("[!] No archive file found in directory.")

                    new_page.close()

                else:
                    print(f"[!] Unknown URL pattern: {current_url}")
                    new_page.close()

                print(f"[+] Done processing '{game}'.")

            except Exception as e:
                print(f"[!] An error occurred: {e}")
                continue

        context.close()
        browser.close()

if __name__ == "__main__":
    main()
