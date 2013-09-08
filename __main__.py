#!/usr/bin/python3

# The command-line runner for the ffmirror program.

import re, sys, argparse
import ffmirror.util as util

def unsilly_import(name):
    mod = __import__(name) # For dotted imports, this _imports_ the module you want, but _returns_ the top-level package.
    for i in name.split('.')[1:]:
        mod = getattr(mod, i)
    return mod

urlres = [ (re.compile("https?://www.fanfiction.net/.*"), unsilly_import('ffmirror.ffnet')) ]

def parse_url(url):
    for reg, mod in urlres:
        if reg.match(url):
            return mod

def download_story(url, **kwargs):
    mod = parse_url(url)
    sid = mod.story_url_re.match(url).group('number')
    md, toc = mod.download_metadata(sid)
    if not kwargs['silent']: print("Found story {}, {} chapters".format(md['title'], md['chapters']))
    if kwargs['dry_run']:
        print('\nMetadata:')
        for i in md:
            print("{}: {}".format(i, md[i]))
        print("\nContents:")
        for i in toc:
            print(i)
        return
    if kwargs['outfile']:
        fn = kwargs['outfile']
    else:
        fn = util.make_filename(md['title']) + ".html"
    del kwargs['outfile']
    with open(fn, 'w') as outfile:
        def progress(n, t):
            if not kwargs['silent']: print("Got chapter {} of {}".format(n+1, len(toc)), end='\r')
        mod.compile_story(md, toc, outfile, callback=progress, **kwargs)
        if not kwargs['silent']: print("", end='\n')

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="A story downloader and formatter for FanFiction.net")
    g = ap.add_mutually_exclusive_group()
    ap.add_argument("--hostname", help="The hostname to connect to", default="www.fanfiction.net")
    ap.add_argument("-o", "--outfile", help="The file to output to", default="")
    g.add_argument("-c", "--contents", action="store_true", help="Generate a table of contents", default=False)
    g.add_argument("--no-headers", action="store_false", help="Suppress chapter headers", default=True, dest='headers')
    ap.add_argument("-s", "--silent", action="store_true", help="Suppress running output", default=False)
    ap.add_argument("-k", "--kindle", action="store_true", help="Format output for a Kindle", default=False)
    ap.add_argument("-d", "--dry-run", action="store_true", help="Dry run (no download, just parse metadata)", default=False)
    ap.add_argument("url", help="A URL for a chapter of the fic")
    args = ap.parse_args()
    download_story(**args.__dict__)
