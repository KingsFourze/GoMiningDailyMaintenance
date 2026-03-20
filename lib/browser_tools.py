import asyncio, time
import zendriver as zd

from typing import Optional, Callable, Coroutine, Any

DEFAULT_SELECTOR_TIMEOUT = 30  # seconds
DEFAULT_LOADING_TIMEOUT = 120  # seconds
POLL_INTERVAL_SECONDS = 0.5  # seconds

async def start_browser(load_cookies: bool):
    '''
    Start the browser and return the browser and the first tab. Optionally load cookies from a file.

    @param load_cookies: If True, load cookies from "cookies.dat" file if it exists.
    @return: A tuple of (browser, tab) where browser is the started browser instance and tab is the first tab of the browser.
    '''
    browser = await zd.start(headless=False)

    tab = await browser.get()
    await tab.set_window_size(width=1920, height=1080)
    if load_cookies:
        await browser.cookies.load("cookies.dat")

    return browser, tab

async def wait_for(tab: zd.Tab, selector: Optional[str] = None, xpath: Optional[str] = None, single: bool = True, timeout_seconds: int = DEFAULT_SELECTOR_TIMEOUT):
    '''
    Wait for an element to appear on the page, using either a CSS selector or an XPath.

    @param tab: The browser tab to search within.
    @param selector: A CSS selector to find the element(s). Mutually exclusive with `xpath`.
    @param xpath: An XPath to find the element(s). Mutually exclusive with `selector`.
    @param single: If True, return a single element. If False, return a list of elements. Default is True.
    @param timeout_seconds: The maximum time to wait for the element(s) to appear before giving up. Default is 30 seconds.
    @return: The found element(s) if they appear within the timeout, or None if they do not.
    '''
    start_time = time.time()
    last_error = None

    # validate input (either selector or xpath must be provided, but not both)
    if (selector is None and xpath is None) or (selector is not None and xpath is not None):
        raise ValueError("Either selector or xpath must be provided, but not both.")
    
    while time.time() - start_time < timeout_seconds:
        try:
            if selector:
                if single:
                    element = await tab.query_selector(selector)
                else:
                    element = await tab.query_selector_all(selector)
            else:
                if single:
                    element = await tab.find_element_by_text(xpath)
                else:
                    element = await tab.find_elements_by_text(xpath)

            if single and element is not None:
                return element
            elif not single and len(element) > 0:
                return element
        except Exception as exc:
            last_error = exc
            pass
        
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    
    if last_error:
        print(f"[DEBUG] Selector '{selector}' not found after {timeout_seconds}s: {last_error}")
    return None

async def wait_for_page_load(tab: zd.Tab, wait_selector: Optional[str] = None, wait_xpath: Optional[str] = None, wait_until : Optional[Callable[[zd.Tab], Coroutine[Any, Any, bool]]] = None, from_url: Optional[str] = None, timeout_seconds: int = DEFAULT_LOADING_TIMEOUT):
    '''
    Wait for the page to load by checking either a specific element (wait_selector or wait_xpath) or a custom condition (wait_until).
    - If `from_url` is provided, it will first wait for the tab to navigate away from that URL, which is useful for waiting for login redirects.
    - If `wait_until` is provided, it will repeatedly call that function until it returns True or times out.
    - If `wait_until` is not provided, it will wait for the element specified by `wait_selector` or `wait_xpath` to appear, which is a common way to check if the page has loaded.

    @param tab: The browser tab to monitor.
    @param wait_selector: A CSS selector for an element that indicates the page has loaded.
    @param wait_xpath: An XPath for an element that indicates the page has loaded.
    @param wait_until: A custom async function that takes the tab as an argument and returns True when the page is considered loaded.
    @param from_url: If provided, the function will first wait for the tab's URL to change from this URL before checking for page load. This is useful for waiting for login redirects.
    @param timeout_seconds: The maximum time to wait for the page to load before giving up.
    @return: True if the page loaded successfully, False if it timed out.
    '''

    await tab
    start_time = time.time()

    # check input validity
    if wait_until is None and wait_selector is None and wait_xpath is None:
        raise ValueError("At least one of wait_until, wait_selector, or wait_xpath must be provided.")
    if (wait_until is not None) and (wait_selector is not None or wait_xpath is not None):
        raise ValueError("wait_until cannot be used together with wait_selector or wait_xpath.")
    if (wait_selector is not None) and (wait_xpath is not None):
        raise ValueError("wait_selector and wait_xpath cannot be used together.")
    
    # wait for redirect done while from_url is provided
    while from_url is not None and tab.url.startswith(from_url):
        if time.time() - start_time >= timeout_seconds:
            print("[ERROR] Waiting for login redirect timed out.")
            return False
        await tab
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    # wait for the page to load
    if wait_until is not None:
        while time.time() - start_time < timeout_seconds:
            try:
                if await wait_until(tab):
                    print("[INFO] Page loaded based on custom condition.")
                    return True
            except Exception as exc:
                print(f"[DEBUG] Error while waiting for custom condition: {exc}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        print("[ERROR] Waiting for page load based on custom condition timed out.")
        return False
    else:
        remaining_time = timeout_seconds - (time.time() - start_time)
        nav = await wait_for(tab, selector=wait_selector, xpath=wait_xpath, timeout_seconds=max(10, remaining_time))
        if nav is None:
            print("[ERROR] Navigator element not found after timeout.")
            return False
        print("[INFO] Navigator element found. Page loaded.")
        return True

async def safe_save_screenshot(tab: zd.Tab, filename: str):
    '''
    Safely save a screenshot of the current tab to the specified filename. If an error occurs during saving, it will catch the exception and print a warning instead of crashing.

    @param tab: The browser tab to capture.
    @param filename: The filename to save the screenshot to.
    '''
    try:
        await tab.save_screenshot(filename)
        print(f"[INFO] Screenshot saved: {filename}")
    except Exception as exc:
        print(f"[WARN] Failed to save screenshot {filename}: {exc}")