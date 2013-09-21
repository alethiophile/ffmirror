# Utilities common to the fanfic site scrapers

import time, urllib.request, urllib.error, re

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
    return rv[1:] # remove extraneous leading space

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
    return re.sub("[^a-z0-9_]", "", title)

def urlopen_retry(url, tries=3, delay=1):
    """Open a URL, with retries on failure. Spoofs user agent to look like Firefox,
    since FFnet 403s the urllib UA."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:21.0) Gecko/20100101 Firefox/21.0"})
    for i in range(tries):
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.URLError as e:
            if i == tries - 1:
                raise e
            time.sleep(delay)
        else:
            return r
        
def unsilly_import(name):
    mod = __import__(name) # For dotted imports, this _imports_ the module you want, but _returns_ the top-level package.
    for i in name.split('.')[1:]:
        mod = getattr(mod, i)
    return mod

