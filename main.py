import sys, os, re, time
from typing import Literal

import asyncio
import zendriver as zd

from lib.browser_tools import start_browser, safe_save_screenshot, wait_for, wait_for_page_load

async def get_service_btn(tab: zd.Tab):
    await tab

    return await wait_for(tab, selector="service-button > button", timeout_seconds=10)

async def check_auth_preloader_gone(t: zd.Tab):
    preloader_for_html_loaded = await t.find_element_by_text("//*[@id='load-preloader']")
    preloader_for_script_loaded = await t.find_element_by_text("//auth-preloader")
    return preloader_for_html_loaded is None and preloader_for_script_loaded is None

async def check_service_btn_state(tab: zd.Tab, service_btn: zd.Element) -> Literal["clickable", "loading", "already_clicked", "unknown"]:
    await tab

    button_text = service_btn.text_all.strip()

    attr = service_btn.attributes
    if "disabled" in attr:
        if re.match(r"\d{2}:\d{2}:\d{2}", button_text):
            print("Service button is in already_clicked state. | Button text:", button_text , "| Button disabled")
            return "already_clicked"
        
        print("Service button is in loading state. | Button text:", button_text, "| Button disabled")
        return "loading"

    if button_text == "Service":
        print("Service button is in clickable state. | Button text:", button_text, "| Button enabled")
        return "clickable"
    
    print("Service button is in unknown state. | Button text:", button_text, "| Button enabled")
    return "unknown"

async def check_and_select_english(tab: zd.Tab, timeout_seconds: int = 15):
    await tab

    # get locale button
    locale_button = await wait_for(tab, xpath="//page-bottom//locale-switcher/div/button", single=True, timeout_seconds=timeout_seconds)
    if locale_button is None:
        print("[WARN] Locale switch button not found after timeout.")
        return "error_finding_locale_button" # locale button not found

    # check if english is already selected
    language_str = locale_button.text_all.strip()
    if language_str == "English":
        print("[INFO] English language already selected.")
        return "already_selected" # already selected
    print("[INFO] Current language:", language_str, "| Clicking locale switch button to select English.")
    await locale_button.scroll_into_view()
    await locale_button.click()

    # select english option
    english_option = await wait_for(
        tab,
        xpath="//modal-locale-switcher//button[contains(@class, 'modal-locale-switcher')]//span[contains(text(), 'English') and contains(@class, 'small')]",
        single=True,
        timeout_seconds=timeout_seconds
    )
    if english_option is None:
        print("[WARN] English option not found after timeout.")
        return "error_finding_english_option" # english option not found
    
    # the clickable element is the parent of the one with "English" text
    while english_option.tag_name != "button":
        english_option = english_option.parent
    await english_option.click()

    await tab
    print("[INFO] English language selected.")
    return "switched" # language switched

async def login_process():
    print("[INFO] Login Mode")

    # start browser
    browser, tab = await start_browser(load_cookies=False)

    try:
        # navigate to the login page
        await tab.get("https://app.gomining.com/login")

        if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
            print("[ERROR] Login page did not load as expected. Please check the page structure.")
            await safe_save_screenshot(tab, "login_page_load_error.png")
            return False

        # check and select english language
        language_status = await check_and_select_english(tab)
        if language_status == "switched":
            if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
                print("[ERROR] Page did not load as expected after switching language.")
                await safe_save_screenshot(tab, "login_page_load_error.png")
                return False
        elif "error" in language_status:
            print("[ERROR] Failed to switch language. Please check the page structure. | error type:", language_status)
            await safe_save_screenshot(tab, "login_language_switch_error.png")
            return False

        # wait for the login form to load, 
        # selector of email input field (#email-or-phone) / selector of password input field (#password) / selector of login button (button[type='submit'])
        email_input = await wait_for(tab, selector="#email-or-phone", timeout_seconds=60)
        password_input = await wait_for(tab, selector="#password", timeout_seconds=1)
        login_btn = await wait_for(tab, selector="button[type='submit']", timeout_seconds=1)
        if not email_input or not password_input or not login_btn:
            print("[ERROR] Login form did not load after retries.")
            await safe_save_screenshot(tab, "login_form_not_found.png")
            return False
        print("[INFO] Login form loaded.")

        # fill in the login form
        email = input("Enter your email: ")
        await email_input.scroll_into_view()
        await email_input.click()
        await email_input.clear_input()
        await email_input.send_keys(email)

        password = input("Enter your password: ")
        await password_input.click()
        await password_input.clear_input()
        await password_input.send_keys(password)

        await login_btn.click()
        print("[INFO] Login button clicked.")

        # wait the TOTP code inputs to load, selector of TOTP code input fields (#code > div > div:nth-child(x) > div > input)
        totp_inputs: list[zd.Element] = []
        for i in range(6):
            totp_input = await wait_for(
                tab,
                selector=f"#code > div > div:nth-child({i+1}) > div > input",
                timeout_seconds=15,
            )
            if totp_input is None:
                print("[ERROR] TOTP input fields did not fully load after retries.")
                await safe_save_screenshot(tab, "totp_inputs_not_found.png")
                return False
            totp_inputs.append(totp_input)
        print("[INFO] TOTP code inputs loaded.")

        while True:
            totp_code = input("Enter your TOTP code: ")
            if len(totp_code) == 6 and totp_code.isdigit():
                break
            print("Invalid TOTP code. Please enter a 6-digit code.")
    
        for i in range(6):
            await totp_inputs[i].click()
            await totp_inputs[i].send_keys(totp_code[i])

        if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone, from_url="https://app.gomining.com/login") or not await wait_for(tab, selector="a[href='/nft-dashboard']", timeout_seconds=30) or await get_service_btn(tab) is None:
            print("[ERROR] Page did not load as expected after login. Please check the page structure.")
            await safe_save_screenshot(tab, "login_page_load_or_service_btn_error.png")
            return False

        # store the cookies after login
        await browser.cookies.save("cookies.dat")
        print("[INFO] Login successful. Cookies saved to cookies.dat.")
    finally:
        await browser.stop()

async def check_if_logged_in(tab: zd.Tab, timeout_seconds: int = 30):
    # check if login button exits or service button loaded
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        if await wait_for(tab, selector="Log in", timeout_seconds=2) is not None:
            print("[ERROR] Login button found. Not logged in.")
            return False

        service_btn = await get_service_btn(tab)
        if service_btn is None:
            print("[ERROR] Service button not found. Please check the page structure.")
            return False

        service_btn_state = await check_service_btn_state(tab, service_btn)
        if service_btn_state == "loading":
            await asyncio.sleep(0.5)
            continue

        if service_btn_state in ["clickable", "already_clicked"]:
            return True
        
        return False
    
    print("[ERROR] Login status check timed out.")
    return False

async def maintenance_process():
    print("[INFO] Maintenance Mode")

    # start browser
    browser, tab = await start_browser(load_cookies=True)

    try:
        # navigate to the page that requires login
        await tab.get("https://app.gomining.com/nft-miners")
        if not await wait_for_page_load(tab, from_url="about:blank", wait_until=check_auth_preloader_gone):
            print("[ERROR] Page did not load as expected. Please check the page structure.")
            await safe_save_screenshot(tab, "maintenance_page_load_error.png")
            return

        # check and select english language
        status = await check_and_select_english(tab)
        if status == "switched":
            await tab.get("https://app.gomining.com/nft-miners")

            # wait for the page to load after switching language
            if not await wait_for_page_load(tab, wait_until=check_auth_preloader_gone):
                print("[ERROR] Page did not load as expected after language switch. Please check the page structure.")
                await safe_save_screenshot(tab, "maintenance_page_load_error_after_language_switch.png")
                return
        elif "error" in status:
            print("[ERROR] Failed to switch language. Please check the page structure. | error type:", status)
            await safe_save_screenshot(tab, "maintenance_language_switch_error.png")
            return

        # wait for the page to load after login, selector of the element that only appears after login (e.g. a[href='/nft-dashboard'])
        if not await check_if_logged_in(tab):
            print("[WARN] Not logged in. Please run the login process first.")
            await safe_save_screenshot(tab, "maintenance_not_logged_in.png")
            return
        print("[INFO] Logged in successfully.")
        
        # start to click the service button
        print("[INFO] Starting to click the service button...")
        start_time = time.time()
        
        while time.time() - start_time < 90:
            # find the service button
            service_btn = await get_service_btn(tab)
            if service_btn is None:
                print("[ERROR] Service button not found. Please check the page structure.")
                await safe_save_screenshot(tab, "maintenance_service_btn_not_found_before_click.png")
                return
            
            # check if the service button is clickable
            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                print("[INFO] Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                print("[INFO] Service button is in loading state. Waiting for it to loading complete...")
                await tab
                await asyncio.sleep(0.5)
                continue
            elif service_btn_state == "unknown":
                print("[ERROR] Service button is in unknown state. Please check the page structure.")
                await safe_save_screenshot(tab, "maintenance_service_btn_unknown_state_before_click.png")
                return

            # click the service button
            await service_btn.click()
            print("[INFO] Service button clicked.")

            # wait for update
            await tab

            # check if the service button is still in clickable, (service-button > button > span.btn__text.hidden-empty) is "Service" text
            service_btn = await get_service_btn(tab)
            if service_btn is None:
                print("[ERROR] Service button not found after click. Please check the page structure.")
                await safe_save_screenshot(tab, "maintenance_service_btn_not_found_after_click.png")
                return

            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                print("[INFO] Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                print("[INFO] Service button is in loading state after click. Waiting for it to loading complete...")
                await tab
                await asyncio.sleep(0.5)
                continue
            elif service_btn_state == "unknown":
                print("[ERROR] Service button is in unknown state after click. Please check the page structure.")
                await safe_save_screenshot(tab, "maintenance_service_btn_unknown_state_after_click.png")
                return

            print("[INFO] Service button is still clickable after click. Retrying...")
        
        print(f"[ERROR] Maintenance loop exceeded 90s timeout without reaching final state.")
        await safe_save_screenshot(tab, "maintenance_timeout_reached.png")
    finally:
        # save the cookies before exit
        await browser.cookies.save("cookies.dat")
        # stop the browser
        await browser.stop()
        
async def main():
    if len(sys.argv) != 2:
        print('''
Usage: python main.py <mode>
Modes:
    - "login" to run the login process
    - "maintenance" to run the maintenance process
        ''')
        return

    mode = sys.argv[1].lower()
    use_virtual_display = sys.platform.startswith("linux")

    if use_virtual_display:
        from pyvirtualdisplay.display import Display

    # clean up old screenshots
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
        print(f'Unknown mode: {mode}')
        print('Please use "login" or "maintenance".')
    return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[INFO] Interrupted by user.")
    except Exception as exc:
        print(f"[ERROR] Unhandled exception: {exc}")
        raise
