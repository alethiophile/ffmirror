# Utilities common to the fanfic site scrapers

import time, urllib.request, urllib.error, re, hashlib, os, json
import urllib.parse, requests
from bs4 import NavigableString  # type: ignore

def fold_string_indiscriminately(s, n=80):
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

def fold_string_discriminately(s, n=80):
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

def make_filename(title):
    title = title.lower().replace(" ", "_")
    return re.sub("[^a-z0-9_.-]", "", title)

def url_hash(url):
    return hashlib.sha256(url.encode()).hexdigest()

class FakeRequest:
    def __init__(self, d):
        self.data = d

    def read(self):
        return self.data

class NetworkFetcher:
    def __init__(self, time_delay=2.0):
        self.last_fetch = {}
        self.delay = time_delay

    def do_fetch(self, url, timeout=30, opener=None):
        headers = { "User-Agent":
                    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:21.0) "
                    "Gecko/20100101 Firefox/21.0" }
        host = urllib.parse.urlsplit(url).netloc
        if host not in self.last_fetch:
            self.last_fetch[host] = 0
        wait = time.time() - self.last_fetch[host]
        if wait < self.delay:
            time.sleep(self.delay - wait)
        self.last_fetch[host] = time.time()

        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()

        return r.content

def urlopen_retry(url, tries=3, delay=1, timeout=30, opener=None,
                  cache_dir='/home/tom/.ffmirror_cache',
                  fetcher=NetworkFetcher()):
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
            data = fetcher.do_fetch(url, timeout, opener)
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

def unsilly_import(name):
    # For dotted imports, this _imports_ the module you want, but _returns_ the
    # top-level package.
    mod = __import__(name)
    for i in name.split('.')[1:]:
        mod = getattr(mod, i)
    return mod

def rectify_strings(d):
    for i in d:
        if isinstance(d[i], NavigableString):
            d[i] = str(d[i])
    return d
