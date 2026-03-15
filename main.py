import sys, re

import asyncio
import zendriver as zd

async def start_browser(load_cookies: bool):
    browser = await zd.start(headless=False)

    tab = await browser.get()
    await tab.set_window_size(width=1920, height=1080)
    if load_cookies:
        await browser.cookies.load("cookies.dat")

    return browser, tab

async def get_service_btn(tab: zd.Tab):
    await tab

    failure_count = 0
    while True:
        try:
            return await tab.wait_for("service-button > button", timeout=10)
        except TimeoutError:
            failure_count += 1
            if failure_count >= 6:
                return None
            continue

async def check_service_btn_state(tab: zd.Tab, service_btn: zd.Element):
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

async def wait_for_page_load(tab: zd.Tab):
    await tab
    while tab.url.startswith("https://app.gomining.com/login"):
        await tab

    # wait the page loaded
    failure_count = 0
    while True:
        # check if the element exits 
        try:
            await tab.wait_for("a[href='/nft-dashboard']", timeout=10)
            print("[INFO] Navigator element found. Page loaded.")
            break
        except TimeoutError:
            failure_count += 1

        if failure_count >= 6:
            return False
    return True

async def check_and_select_english(tab: zd.Tab):
    await tab

    # get locale button
    while True:
        try:
            locale_button = await tab.wait_for("locale-switcher > div > button", timeout=5)
            break
        except TimeoutError:
            print("[WARN] English language option not found.")

    # check if english is already selected
    language_str = locale_button.text_all.strip()
    if language_str == "English":
        print("[INFO] English language already selected.")
        return False # already selected
    await locale_button.click()

    # select english option
    while True:
        try:
            english_option = await tab.wait_for("modal-locale-switcher > modal > div > div.modal-body.hidden-empty > div > div:nth-child(1) > button", timeout=5)
            break
        except TimeoutError:
            continue
    await english_option.click()

    await tab
    print("[INFO] English language selected.")
    return True # language switched

async def login_process():
    print("[INFO] Login Mode")

    # start browser
    browser, tab = await start_browser(load_cookies=False)

    try:
        # navigate to the login page
        await tab.get("https://app.gomining.com/login")

        # check and select english language
        if await check_and_select_english(tab):
            await tab.get("https://app.gomining.com/login")

        # wait for the login form to load, 
        # selector of email input field (#email-or-phone) / selector of password input field (#password) / selector of login button (button[type='submit'])
        while True:
            try:
                email_input = await tab.wait_for("#email-or-phone", timeout=5)
                password_input = await tab.wait_for("#password", timeout=5)
                login_btn = await tab.wait_for("button[type='submit']", timeout=5)
                break
            except TimeoutError:
                continue
        print("[INFO] Login form loaded.")

        # fill in the login form
        email = input("Enter your email: ")
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
        while True:
            try:
                totp_inputs : list[zd.Element] = []
                for i in range(6):
                    totp_input = await tab.wait_for(f"#code > div > div:nth-child({i+1}) > div > input", timeout=5)
                    totp_inputs.append(totp_input)
                break
            except TimeoutError:
                continue
        print("[INFO] TOTP code inputs loaded.")

        while True:
            totp_code = input("Enter your TOTP code: ")
            if len(totp_code) == 6 and totp_code.isdigit():
                break
            print("Invalid TOTP code. Please enter a 6-digit code.")
    
        for i in range(6):
            await totp_inputs[i].click()
            await totp_inputs[i].send_keys(totp_code[i])

        if not await wait_for_page_load(tab) or await get_service_btn(tab) is None:
            print("[ERROR] Page did not load as expected after login. Please check the page structure.")
            return False

        # store the cookies after login
        await browser.cookies.save("cookies.dat")
        print("[INFO] Login successful. Cookies saved to cookies.dat.")
    finally:
        await browser.stop()

async def check_if_logged_in(tab: zd.Tab):
    # check if login button exits or service button loaded
    while True:
        try:
            await tab.wait_for(text="Log in", timeout=5)
            print("[ERROR] Login button found. Not logged in.")
            return False
        except TimeoutError:
            pass

        service_btn = await get_service_btn(tab)
        if service_btn is None:
            print("[ERROR] Service button not found. Please check the page structure.")
            return False

        service_btn_state = await check_service_btn_state(tab, service_btn)
        if service_btn_state == "loading":
            continue

        if service_btn_state in ["clickable", "already_clicked"]:
            return True
        
        return False

async def maintenance_process():
    print("[INFO] Maintenance Mode")

    # start browser
    browser, tab = await start_browser(load_cookies=True)

    try:
        # navigate to the page that requires login
        await tab.get("https://app.gomining.com/nft-miners")

        # check and select english language
        if await check_and_select_english(tab):
            await tab.get("https://app.gomining.com/nft-miners")

        # check page loaded
        if not await wait_for_page_load(tab):
            print("[ERROR] Page did not load as expected. Please check the page structure.")
            return False

        # wait for the page to load after login, selector of the element that only appears after login (e.g. a[href='/nft-dashboard'])
        if not await check_if_logged_in(tab):
            print("[WARN] Not logged in. Please run the login process first.")
            await browser.stop()
            return
        print("[INFO] Logged in successfully.")
        
        # start to click the service button
        print("[INFO] Starting to click the service button...")
        while True:
            # find the service button
            service_btn = await get_service_btn(tab)
            if service_btn is None:
                print("[ERROR] Service button not found. Please check the page structure.")
                return
            
            # check if the service button is clickable
            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                print("[INFO] Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                print("[INFO] Service button is in loading state. Waiting for it to loading complete...")
                await tab
                continue
            elif service_btn_state == "unknown":
                print("[ERROR] Service button is in unknown state. Please check the page structure.")
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
                return

            service_btn_state = await check_service_btn_state(tab, service_btn)
            if service_btn_state == "already_clicked":
                print("[INFO] Exiting maintenance process.")
                return
            elif service_btn_state == "loading":
                print("[INFO] Service button is in loading state after click. Waiting for it to loading complete...")
                await tab
                continue
            elif service_btn_state == "unknown":
                print("[ERROR] Service button is in unknown state after click. Please check the page structure.")
                return

            print("[INFO] Service button is still clickable after click. Retrying...")
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
    asyncio.run(main())
