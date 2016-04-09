#!/usr/bin/python3

# The command-line runner for the ffmirror program. Since the module and mirror
# APIs are by necessity somewhat primitive, this contains several user-interface
# functions that make the semantics nice and easy. These are designed for
# command-line use; other applications should probably use the separate module
# APIs.

import re, sys, argparse, os
import ffmirror.util as util
import ffmirror.mirror as mirror
import ffmirror.ffnet
from ffmirror import sites, urlres

cur_mirror = mirror.FFMirror('.', use_ids=True)

def parse_url(url):
    """Given a fanfiction URL (either story or author), this function will return
    the module that deals with the correct site. It does so by checking the
    regexes in urlres.

    """
    for reg, mod in urlres:
        if reg.match(url):
            return mod

def download_story(url, **kwargs):
    if kwargs['update']:
        o = mirror.read_from_file(url)
        ufn = url
        mod = sites[o['site']]
        #url = mod.story_url.format(number=o['id'], chapter=1, hostname=mod.hostname)
        url = mod.get_story_url(o)
    else:
        mod = parse_url(url)
    o = mod.story_url_re.match(url)
    sid = o.group('number')
    mod.hostname = o.group('hostname')
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
    if kwargs['update']:
        if not cur_mirror.check_update(md, ufn):
            if not kwargs['silent']: print("Nothing to do (up to date)")
            return
    if kwargs['outfile']:
        fn = kwargs['outfile']
    else:
        if kwargs['kindle']:
            fn = util.make_filename(md['title']) + ".txt"
        else:
            fn = util.make_filename(md['title']) + ".html"
    del kwargs['outfile']
    with open(fn, 'w') as outfile:
        def progress(n, t):
            if not kwargs['silent']: print("Got chapter {} of {}".format(n+1, len(toc)), end='\r')
        mod.compile_story(md, toc, outfile, callback=progress, **kwargs)
        if not kwargs['silent']: print("", end='\n')

def run_dl():
    ap = argparse.ArgumentParser(description="Download a single story as a plain file")
    ap.add_argument("-s", "--silent", action="store_true", help="Suppress running output", default=False)
    g = ap.add_mutually_exclusive_group()
    ap.add_argument("-o", "--outfile", help="The file to output to", default="")
    g.add_argument("-c", "--contents", action="store_true", help="Generate a table of contents", default=False)
    g.add_argument("--no-headers", action="store_false", help="Suppress chapter headers", default=True, dest='headers')
    ap.add_argument("-k", "--kindle", action="store_true", help="Format output for a Kindle (now deprecated, use ebook-convert)", default=False)
    ap.add_argument("-d", "--dry-run", action="store_true", help="Dry run (no download, just parse metadata)", default=False)
    ap.add_argument("-u", "--update", action="store_true", help="Update an existing file", default=False)
    ap.add_argument("url", help="A URL for a chapter of the fic, or (with -u) filename for update", default=None)
    args = ap.parse_args()
    download_story(**args.__dict__)

def download_list(url, ls=False, silent=False, getall=False, dry_run=False, **kwargs):
    mod = parse_url(url)
    uid = mod.user_url_re.match(url).group('number')
    auth, fav = mod.download_list(uid)
    sl = fav if ls else auth
    if not getall:
        nsl = [i for i in sl if cur_mirror.check_update(i)]
    else:
        nsl = sl
    if not silent and len(auth) > 0: print("Got {} (of {}) stories from author {}".format(len(nsl), len(sl), auth[0]['author']))
    if dry_run:
        for i in sl:
            print(i)
        return
    cur_mirror.update_tags(nsl)
    lsl = 0
    def progress(i, n):
        nonlocal lsl
        if not silent:
            if type(n) == tuple:
                print("Acquiring story '{}' (#{}/{})".format(n[0]['title'], i+1, len(nsl)))
                lsl = len(n[1])
            else:
                print("Got chapter {} of {}".format(i+1, lsl), end='\r')
                if i == lsl - 1:
                    print("\n", end="")
    cur_mirror.update_list(nsl, callback=progress)

def run_add():
    ap = argparse.ArgumentParser(description="Add an author's corpus or favorites to a mirror, or update them")
    ap.add_argument("-s", "--silent", action="store_true", help="Suppress running output", default=False)
    ap.add_argument("-f", "--favorites", dest='ls', action="store_true", default=False, help="Get author's favorites rather than their corpus")
    ap.add_argument("-a", "--all", dest='getall', action="store_true", default=False, help="Download all stories without checking if already present")
    ap.add_argument("-d", "--dry-run", action="store_true", default=False, help="Dry run (only parse list and print)")
    ap.add_argument("url", help="A URL for an author's profile")
    args = ap.parse_args()
    download_list(**args.__dict__)

def update_mirror(silent=False):
    m = cur_mirror.read_entries()
    for n,i in enumerate(sorted(m.keys())):
        if not silent: print("Author '{}' (#{}/{})".format(m[i][0]['author'], n+1, len(m)))
        mod = sites[m[i][0]['site']]
        #url = mod.user_url.format(number=m[i][0]['authorid'], hostname=mod.hostname)
        url = mod.get_user_url(m[i][0])
        download_list(url, silent=silent)

def run_update():
    ap = argparse.ArgumentParser(description="Update an entire mirror from the Web site")
    ap.add_argument("-s", "--silent", action="store_true", help="Suppress running output", default=False)
    args = ap.parse_args()
    update_mirror(**args.__dict__)

def do_cache():
    cur_mirror.make_cache()
    
actions = { 'ffdl': run_dl,
            'ffadd': run_add,
            'ffup': run_update,
            'ffcache': do_cache }

if __name__ == "__main__":
    pn = os.path.split(sys.argv[0])[1]
    if not pn in actions:
        sys.argv.pop(0)
        if len(sys.argv) == 0:
            sys.argv.append("")
        pn = os.path.split(sys.argv[0])[1]
    if pn in actions:
        actions[pn]()
    else:
        print("No such module available")
        print("Try one of:")
        for i in actions.keys():
            print(i)
