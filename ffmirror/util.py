# Utilities common to the fanfic site scrapers

from __future__ import annotations

import time, urllib.request, urllib.error, re, hashlib, os, json
import urllib.parse, requests, atexit, sys, signal
try:
    import cloudscraper
except Exception:
    cloudscraper = None
from bs4 import NavigableString  # type: ignore
from attrs import define
from typing import Dict, Optional, Any, Callable

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    import undetected_chromedriver.v2 as uc
    from selenium.webdriver.support.wait import WebDriverWait
except Exception:
    webdriver = None

def fold_string_indiscriminately(s: str, n: int = 80) -> str:
    """Folds a string (insert line-breaks where appropriate, to format
    on a display of no more than n columns) indiscriminately, meaning
    lose all existing whitespace formatting. This is the equivalent of
    doing an Emacs fill-paragraph on the string in question, though it
    doesn't break around double linefeeds like that function does."""
    l = s.split()
    rv = ""
    cl = 0
    for i in l:
        if cl + len(i) + 1 < n:
            rv += ' ' + i
            cl += len(i) + 1
        else:
            rv += ' \n' + i
            cl = len(i)
    return rv[1:]  # remove extraneous leading space

def fold_string_discriminately(s: str, n: int = 80) -> str:
    """Folds a string discriminately, that is, preserving existing
    hard line breaks in the original. This is the equivalent of
    passing the string to fold -s."""
    l = s.splitlines()
    rv = ""
    for i in l:
        if len(i) < n:
            rv += i + '\n'
        else:
            rv += fold_string_indiscriminately(i, n) + '\n'
    return rv

def make_filename(title: str) -> str:
    title = title.lower().replace(" ", "_")
    return re.sub("[^a-z0-9_.-]", "", title)

def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()

class FakeRequest:
    def __init__(self, d: bytes) -> None:
        self.data = d

    def read(self) -> bytes:
        return self.data

class NetworkFetcher:
    def __init__(self, time_delay: float = 2.0):
        self.last_fetch: Dict[str, float] = {}
        self.delay = time_delay

    def do_fetch(self, url: str, timeout: int = 30,
                 use_cloudscraper: bool = False) -> bytes:
        headers = { "User-Agent":
                    # "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:21.0) "
                    # "Gecko/20100101 Firefox/21.0" }
                    "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:76.0) "
                    "Gecko/20100101 Firefox/76.0" }
        host = urllib.parse.urlsplit(url).netloc
        if host not in self.last_fetch:
            self.last_fetch[host] = 0
        wait = time.time() - self.last_fetch[host]
        if wait < self.delay:
            time.sleep(self.delay - wait)
        self.last_fetch[host] = time.time()

        if use_cloudscraper:
            if cloudscraper is None:
                raise ValueError("cloudscraper not supported")
            fetcher = cloudscraper.create_scraper(
                browser={
                    'browser': 'firefox',
                    'platform': 'windows',
                    'mobile': False,
                    'desktop': True,
                })
            headers = {}
        else:
            fetcher = requests
        r = fetcher.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()

        return r.content

def urlopen_retry(url: str, tries: int = 3, delay: float = 1.0,
                  timeout: int = 30,
                  cache_dir: str = '/home/tom/.ffmirror_cache',
                  fetcher: NetworkFetcher =
                  NetworkFetcher(),
                  use_cloudscraper: bool = False) -> Optional[FakeRequest]:
    """Open a URL, with retries on failure. Spoofs user agent to look like Firefox,
    since FFnet 403s the urllib UA."""
    fn = None
    if cache_dir is not None:
        uh = url_hash(url)
        fn = os.path.join(cache_dir, uh)
        if os.path.exists(fn) and os.stat(fn).st_mtime > time.time() - 43200:
            try:
                with open(fn) as inp:
                    r = json.load(inp)
                return FakeRequest(r['data'].encode())
            except Exception:
                pass
    for i in range(tries):
        try:
            # r = open_func(req, timeout=timeout)
            data = fetcher.do_fetch(url, timeout,
                                    use_cloudscraper=use_cloudscraper)
        except urllib.error.URLError as e:
            if i == tries - 1:
                raise e
            time.sleep(delay)
        else:
            if fn is not None:
                try:
                    o = { 'data': data.decode() }
                except UnicodeDecodeError:
                    print(url)
                    print(repr(data))
                    raise
                with open(fn, 'w') as out:
                    json.dump(o, out)
                return FakeRequest(o['data'].encode())
            return FakeRequest(data)
    return None

def rectify_strings(d: Dict[str, Any]) -> Dict[str, Any]:
    for i in d:
        if isinstance(d[i], NavigableString):
            d[i] = str(d[i])
    return d

global_driver = None
hooks_set = False

def set_hooks():
    global hooks_set

    def quit_driver():
        global global_driver
        if global_driver is None:
            return
        try:
            global_driver.quit()
        except Exception:
            pass

    def exh(t, v, tb):
        quit_driver()
        return sys.__excepthook__(t, v, tb)

    # ideally we might set excepthook here in order to handle non-normal exits;
    # I leave it unset for easier debugging of issues involving the browser
    # sys.excepthook = exh

    atexit.register(quit_driver)

    hooks_set = True

def get_webdriver():
    """Get a webdriver. If Selenium is not available or no driver can be created,
    return None; in this case, ffmirror will fall back on direct HTTP requests
    (not all sites supported).

    """
    if webdriver is None:
        return None

    if not hooks_set:
        set_hooks()

    global global_driver

    if global_driver is None:
        global_driver = uc.Chrome()

    return global_driver

def restart_webdriver():
    global global_driver
    if global_driver is None:
        return None

    global_driver.quit()
    global_driver = None

    return get_webdriver()

class TimeoutException(BaseException):
    pass

def sigalrm_handler(signum, frame):
    raise TimeoutException()

signal.signal(signal.SIGALRM, sigalrm_handler)

class BrowserFetcher:
    """A class to handle using the browser driver to fetch pages. Contains a
    reference to the global driver, and imposes a global delay on all
    fetches. The get_html() method simply downloads a page and returns the HTML
    contents from the DOM; more sophisticated applications may manipulate the
    driver attribute directly. Any manual driver manipulation must call
    wait_for_delay() between fetches in order to respect the rate limit.

    """
    fetch_delay = 2.0
    last_fetch = 0.0
    # Timeout used for waiting until the site displays
    display_timeout = 10
    # Timeout for handling buggy webdriver
    restart_timeout = 20

    def __init__(self, test: Any = None) -> None:
        # test is a webdriver wait function; it takes a driver as its only
        # argument, and returns True if the site has finished loading

        # this is used to detect whether we've passed the Cloudflare check
        if test is None:
            self.test: Callable[[Any], bool] = lambda x: True
        else:
            self.test = test

        self.driver = get_webdriver()

    @classmethod
    def wait_for_delay(cls) -> None:
        now = time.time()
        since_last = now - cls.last_fetch
        if since_last < cls.fetch_delay:
            time.sleep(cls.fetch_delay - since_last)
        cls.update_last_fetch()

    @classmethod
    def update_last_fetch(cls) -> None:
        cls.last_fetch = time.time()

    def get_html(self, url: str, tries: int = 3) -> str:
        self.wait_for_delay()
        while True:
            signal.alarm(self.restart_timeout)
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, timeout=10).until(self.test)
                el = self.driver.find_element(By.TAG_NAME, "html")
                r = el.get_attribute("outerHTML")
                self.update_last_fetch()
            except TimeoutException:
                self.driver = restart_webdriver()
                tries -= 1
                if tries <= 0:
                    raise
            else:
                signal.alarm(0)
                break
        return r

@define
class JobStatus:
    type: str
    name: str
    progress: Optional[int] = None
    total: Optional[int] = None
    info: Optional[str] = None
