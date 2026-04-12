import sys, os, re, time, json, logging
from typing import Literal

import asyncio
import zendriver as zd
import pyotp

from lib.browser_tools import (
    start_browser,
    safe_save_screenshot,
    wait_for,
    wait_for_page_load,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s][%(levelname)s] %(funcName)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
for logger_name in [
    "zendriver",
    "uc.connection",
]:
    zl = logging.getLogger(logger_name)
    zl.setLevel(logging.WARNING)
logger = logging.getLogger("gomining_daily_claim")

# ========== Credentials ==========

CREDENTIALS_FILE = "credentials.json"


def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            return json.load(f)
    return None


def save_credentials(email: str, password: str, totp_secret: str):
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"email": email, "password": password, "totp_secret": totp_secret}, f)


def generate_totp_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


# ========== Browser Tools ==========


async def check_auth_preloader_gone(t: zd.Tab):
    preloader_for_html_loaded = await t.find_element_by_text(
        "//*[@id='load-preloader']"
    )
    preloader_for_script_loaded = await t.find_element_by_text("//auth-preloader")
    return preloader_for_html_loaded is None and preloader_for_script_loaded is None


async def check_and_select_english(tab: zd.Tab, timeout_seconds: int = 15):
    await tab
    locale_button = await wait_for(
        tab,
        xpath="//page-bottom//locale-switcher/div/button",
        single=True,
        timeout_seconds=timeout_seconds,
    )
    if locale_button is None:
        logger.warning("Locale switch button not found after timeout.")
        return "error_finding_locale_button"

    language_str = locale_button.text_all.strip()
    if language_str == "English":
        logger.info("English language already selected.")
        return "already_selected"

    logger.info(
        f"Current language: {language_str} | Clicking locale switch button to select English."
    )
    await locale_button.scroll_into_view()
    await locale_button.click()

    english_option = await wait_for(
        tab,
        xpath="//modal-locale-switcher//button[contains(@class, 'modal-locale-switcher')]//span[contains(text(), 'English') and contains(@class, 'small')]",
        single=True,
        timeout_seconds=timeout_seconds,
    )
    if english_option is None:
        logger.warning("English option not found after timeout.")
        return "error_finding_english_option"

    while english_option.tag_name != "button":
        english_option = english_option.parent
    await english_option.click()

    await tab
    logger.info("English language selected.")
    return "switched"


async def wait_for_login_page(tab: zd.Tab, timeout_seconds: int = 60) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        await tab
        current_url = tab.url
        if "login" in current_url:
            email_input = await tab.query_selector("#email-or-phone")
            if email_input is not None:
                return True
        elif (
            current_url.startswith("https://app.gomining.com/")
            and "login" not in current_url
        ):
            await tab.get("https://app.gomining.com/login")
        await asyncio.sleep(0.5)
    return False


async def get_service_btn(tab: zd.Tab):
    await tab
    return await wait_for(tab, selector="service-button > button", timeout_seconds=10)


async def check_service_btn_state(
    tab: zd.Tab, service_btn: zd.Element
) -> Literal["clickable", "loading", "already_clicked", "unknown"]:
    await tab
    button_text = service_btn.text_all.strip()
    attr = service_btn.attributes

    if "disabled" in attr:
        if re.match(r"\d{2}:\d{2}:\d{2}", button_text):
            logger.info(
                f"Service button is in already_clicked state. | Button text: {button_text} | Button disabled"
            )
            return "already_clicked"
        logger.info(
            f"Service button is in loading state. | Button text: {button_text} | Button disabled"
        )
        return "loading"

    if button_text == "Service":
        logger.info(
            f"Service button is in clickable state. | Button text: {button_text} | Button enabled"
        )
        return "clickable"

    logger.info(
        f"Service button is in unknown state. | Button text: {button_text} | Button enabled"
    )
    return "unknown"


# ========== Login ==========


async def fill_login_form(
    tab: zd.Tab, email: str, password: str, totp_secret: str
) -> bool:
    email_input = await wait_for(tab, selector="#email-or-phone", timeout_seconds=60)
    password_input = await wait_for(tab, selector="#password", timeout_seconds=1)
    login_btn = await wait_for(tab, selector="button[type='submit']", timeout_seconds=1)
    if not email_input or not password_input or not login_btn:
        return False

    await email_input.scroll_into_view()
    await asyncio.sleep(0.3)
    await email_input.click()
    await asyncio.sleep(0.1)
    await email_input.clear_input()
    await email_input.send_keys(email)

    await asyncio.sleep(0.2)
    await password_input.click()
    await asyncio.sleep(0.1)
    await password_input.clear_input()
    await password_input.send_keys(password)

    await asyncio.sleep(0.3)
    await login_btn.click()

    totp_inputs: list[zd.Element] = []
    for i in range(6):
        totp_input = await wait_for(
            tab,
            selector=f"#code > div > div:nth-child({i + 1}) > div > input",
            timeout_seconds=15,
        )
        if totp_input is None:
            return False
        totp_inputs.append(totp_input)

    totp_code = generate_totp_code(totp_secret)
    for i in range(6):
        await asyncio.sleep(0.2)
        await totp_inputs[i].click()
        await asyncio.sleep(0.1)
        await totp_inputs[i].send_keys(totp_code[i])

    return True


async def login_process():
    logger.info("Login Mode")

    saved_creds = load_credentials()
    browser, tab = await start_browser(load_cookies=False)

    try:
        await tab.get("https://app.gomining.com/login")

        if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
            logger.error("Login page did not load as expected.")
            await safe_save_screenshot(tab, "login_page_load_error.png")
            return False

        language_status = await check_and_select_english(tab)
        if language_status == "switched":
            if not await wait_for_login_page(tab):
                logger.error("Login page did not load after language switch.")
                await safe_save_screenshot(
                    tab, "login_page_not_found_after_language_switch.png"
                )
                return False
        elif "error" in language_status:
            logger.error(f"Failed to switch language. | error type: {language_status}")
            await safe_save_screenshot(tab, "login_language_switch_error.png")
            return False

        if saved_creds:
            email = saved_creds.get("email", "")
            password = saved_creds.get("password", "")
            totp_secret = saved_creds.get("totp_secret", "")
            logger.info("Loaded credentials from file.")
        else:
            email = input("Enter your email: ")
            password = input("Enter your password: ")
            while True:
                totp_secret = input("Enter your TOTP secret (base32): ")
                if totp_secret:
                    break
                print("Invalid TOTP secret.")

        if not await fill_login_form(tab, email, password, totp_secret):
            logger.error("Failed to fill login form.")
            await safe_save_screenshot(tab, "login_fill_form_error.png")
            return False

        logger.info("Login button clicked.")

        if (
            not await wait_for_page_load(
                tab,
                wait_until=check_auth_preloader_gone,
                from_url="https://app.gomining.com/login",
            )
            or not await wait_for(
                tab, selector="a[href='/nft-dashboard']", timeout_seconds=30
            )
            or await get_service_btn(tab) is None
        ):
            logger.error("Page did not load as expected after login.")
            await safe_save_screenshot(tab, "login_page_load_or_service_btn_error.png")
            return False

        save_credentials(email, password, totp_secret)
        await browser.cookies.save("cookies.dat")
        logger.info("Login successful. Cookies and credentials saved.")
    finally:
        await browser.stop()


async def check_if_logged_in(tab: zd.Tab, timeout_seconds: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if await wait_for(tab, selector="Log in", timeout_seconds=2) is not None:
            return False

        service_btn = await get_service_btn(tab)
        if service_btn is None:
            return False

        service_btn_state = await check_service_btn_state(tab, service_btn)
        if service_btn_state == "loading":
            await asyncio.sleep(0.5)
            continue

        if service_btn_state in ["clickable", "already_clicked"]:
            return True

        return False

    return False


async def attempt_login_with_credentials(tab: zd.Tab) -> bool:
    creds = load_credentials()
    if not creds:
        return False

    email = creds.get("email", "")
    password = creds.get("password", "")
    totp_secret = creds.get("totp_secret", "")

    if not email or not password or not totp_secret:
        return False

    await tab.get("https://app.gomining.com/login")
    if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
        return False

    if not await fill_login_form(tab, email, password, totp_secret):
        return False

    return (
        await wait_for_page_load(
            tab,
            wait_until=check_auth_preloader_gone,
            from_url="https://app.gomining.com/login",
        )
        and await wait_for(tab, selector="a[href='/nft-dashboard']", timeout_seconds=30)
        is not None
        and await get_service_btn(tab) is not None
    )


# ========== Maintenance ==========


async def maintenance_process():
    logger.info("Maintenance Mode")

    browser, tab = await start_browser(load_cookies=True)

    try:
        await tab.get("https://app.gomining.com/nft-miners")
        if not await wait_for_page_load(
            tab, from_url="about:blank", wait_until=check_auth_preloader_gone
        ):
            logger.error("Page did not load as expected.")
            await safe_save_screenshot(tab, "maintenance_page_load_error.png")
            return

        status = await check_and_select_english(tab)
        if status == "switched":
            if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
                logger.error("Page did not load as expected after language switch.")
                await safe_save_screenshot(
                    tab, "maintenance_page_load_error_after_language_switch.png"
                )
                return
        elif "error" in status:
            logger.error(f"Failed to switch language. | error type: {status}")
            await safe_save_screenshot(tab, "maintenance_language_switch_error.png")
            return

        if not await check_if_logged_in(tab):
            logger.warning(
                "Not logged in. Attempting to login with saved credentials..."
            )
            await tab.get("https://app.gomining.com/login")
            await asyncio.sleep(5)
            if not await wait_for_login_page(tab):
                logger.error("Login page did not load.")
                await safe_save_screenshot(tab, "maintenance_login_page_not_found.png")
                return
            if not await attempt_login_with_credentials(tab):
                logger.error("Auto-login failed. Please run login mode first.")
                await safe_save_screenshot(tab, "maintenance_auto_login_failed.png")
                return
            logger.info("Auto-login successful via saved credentials.")
            await tab.get("https://app.gomining.com/nft-miners")
            if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
                logger.error("Page did not load as expected after auto-login.")
                await safe_save_screenshot(
                    tab, "maintenance_page_load_error_after_auto_login.png"
                )
                return

        logger.info("Logged in successfully.")
        logger.info("Starting to click the service button...")

        start_time = time.time()
        while time.time() - start_time < 90:
            service_btn = await get_service_btn(tab)
            if service_btn is None:
                logger.error(
                    "Service button not found. Please check the page structure."
                )
                await safe_save_screenshot(
                    tab, "maintenance_service_btn_not_found_before_click.png"
                )
                return

            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                logger.info("Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                logger.info(
                    "Service button is in loading state. Waiting for it to loading complete..."
                )
                await tab
                await asyncio.sleep(0.5)
                continue
            elif service_btn_state == "unknown":
                logger.error(
                    "Service button is in unknown state. Please check the page structure."
                )
                await safe_save_screenshot(
                    tab, "maintenance_service_btn_unknown_state_before_click.png"
                )
                return

            await service_btn.click()
            logger.info("Service button clicked.")

            await tab
            service_btn = await get_service_btn(tab)
            if service_btn is None:
                logger.error("Service button not found after click.")
                await safe_save_screenshot(
                    tab, "maintenance_service_btn_not_found_after_click.png"
                )
                return

            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                logger.info("Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                logger.info(
                    "Service button is in loading state after click. Waiting for it to loading complete..."
                )
                await tab
                await asyncio.sleep(0.5)
                continue
            elif service_btn_state == "unknown":
                logger.error("Service button is in unknown state after click.")
                await safe_save_screenshot(
                    tab, "maintenance_service_btn_unknown_state_after_click.png"
                )
                return

            logger.info("Service button is still clickable after click. Retrying...")

        logger.error(
            "Maintenance loop exceeded 90s timeout without reaching final state."
        )
        await safe_save_screenshot(tab, "maintenance_timeout_reached.png")
    finally:
        await browser.cookies.save("cookies.dat")
        await browser.stop()


# ========== Main ==========


async def main():
    if len(sys.argv) != 2:
        print("""
Usage: python main.py <mode>
Modes:
    - "login" to run the login process
    - "maintenance" to run the maintenance process
        """)
        return

    mode = sys.argv[1].lower()
    use_virtual_display = sys.platform.startswith("linux")

    if use_virtual_display:
        from pyvirtualdisplay.display import Display

    screen_shots = [i for i in os.listdir() if i.endswith(".png")]
    for screenshot in screen_shots:
        os.remove(screenshot)

    if mode == "login":
        if use_virtual_display:
            display = Display(backend="xvfb", size=(1920, 1080))
            display.start()
        try:
            await login_process()
        finally:
            if use_virtual_display:
                display.stop()
    elif mode == "maintenance":
        if use_virtual_display:
            display = Display(backend="xvfb", size=(1920, 1080))
            display.start()
        try:
            await maintenance_process()
        finally:
            if use_virtual_display:
                display.stop()
    else:
        logger.error(f"Unknown mode: {mode}")
        print('Please use "login" or "maintenance".')


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as exc:
        logger.error(f"Unhandled exception: {exc}")
        raise
