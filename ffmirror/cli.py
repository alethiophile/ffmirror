#!/usr/bin/env python3

# The command-line runner for the ffmirror program. Since the module and mirror
# APIs are by necessity somewhat primitive, this contains several
# user-interface functions that make the semantics nice and easy. These are
# designed for command-line use; other applications should probably use the
# separate module APIs.

import sys, argparse, os, json
from . import util, mirror, metadb, site_modules
from .core import url_res, DownloadModule
from typing import Optional
from pathlib import Path
import click

cur_mirror = mirror.FFMirror('.', use_ids=True)

def parse_url(url: str) -> Optional[DownloadModule]:
    """Given a fanfiction URL (either story or author), this function will return
    the module that deals with the correct site. It does so by checking the
    regexes in urlres.

    """
    for reg, mod in url_res:
        if reg.match(url):
            return mod
    return None

def download_story(url: str, silent: bool = False,
                   contents: bool = True, update: bool = False,
                   dry_run: bool = False,
                   outfile: Optional[str] = None) -> None:
    if update:
        t = mirror.read_from_file(url)
        if t is None:
            print(f"Couldn't read file {url}", file=sys.stderr)
            sys.exit(1)
        ufn = url
        mod = site_modules[t.site]
        url = mod.get_story_url(t)
    else:
        tv = parse_url(url)
        assert tv is not None
        mod = tv
    o = mod.story_url_re.match(url)
    assert o is not None
    sid = o.group('sid')
    md, toc = mod.download_metadata(sid)
    if not silent:
        print("Found story {}, {} chapters".
              format(md.title, md.chapters))
    if dry_run:
        print('\nMetadata:')
        d = md.to_dict()
        for i in d:
            print("{}: {}".format(i, d[i]))
        print("\nContents:")
        for c in toc:
            print(c)
        return
    if update:
        if not cur_mirror.check_update(md, ufn):
            if not silent:
                print("Nothing to do (up to date)")
            return
    if outfile:
        fn = outfile
    else:
        fn = util.make_filename(md.title) + ".html"
    with open(fn, 'w') as out_fo:
        def progress(n, t):
            if not silent:
                print("Got chapter {} of {}".format(n + 1, len(toc)), end='\r')
        mod.compile_story(md, toc, out_fo, callback=progress,
                          contents=contents)
        if not silent:
            print("", end='\n')

def run_dl() -> None:
    ap = argparse.ArgumentParser(
        description="Download a single story as a plain file")
    ap.add_argument("-s", "--silent", action="store_true",
                    help="Suppress running output", default=False)
    g = ap.add_mutually_exclusive_group()
    ap.add_argument("-o", "--outfile", help="The file to output to",
                    default="")
    g.add_argument("-c", "--contents", action="store_true",
                   help="Generate a table of contents", default=False)
    ap.add_argument("-d", "--dry-run", action="store_true",
                    help="Dry run (no download, just parse metadata)",
                    default=False)
    ap.add_argument("-u", "--update", action="store_true",
                    help="Update an existing file", default=False)
    ap.add_argument("url", help="A URL for a chapter of the fic, or (with -u) filename for update",  # noqa: E501
                    default=None)
    args = ap.parse_args()
    download_story(**args.__dict__)

def download_list(url, ls=False, silent=False, getall=False, dry_run=False,
                  write_favs=False, **kwargs) -> None:
    mod = parse_url(url)
    assert mod is not None
    o = mod.user_url_re.match(url)
    assert o is not None
    uid = o.group('aid')
    auth, fav, info = mod.download_list(uid)
    if write_favs:
        dn = "{}-{}-{}".format(util.make_filename(info.name),
                               info.site, info.id)
        os.makedirs(dn, exist_ok=True)
        with open(os.path.join(dn, 'favorites.json'), 'w') as out:
            json.dump({'info': info, 'favs': fav}, out, sort_keys=True,
                      indent=1)
    sl = fav if ls else auth
    if not getall:
        nsl = [i for i in sl if cur_mirror.check_update(i)]
    else:
        nsl = sl
    if not silent and len(auth) > 0:
        print("Got {} (of {}) stories from author {}".
              format(len(nsl), len(sl), info.name))
    if dry_run:
        for i in sl:
            print(i)
        return
    cur_mirror.update_tags(nsl)
    lsl = 0

    def progress(i, n) -> None:
        nonlocal lsl
        if not silent:
            if type(n) == tuple:
                print("Acquiring story '{}' (#{}/{})".
                      format(n[0]['title'], i + 1, len(nsl)))
                lsl = len(n[1])
            else:
                print("Got chapter {} of {}".format(i + 1, lsl), end='\r')
                if i == lsl - 1:
                    print("\n", end="")
    cur_mirror.update_list(nsl, callback=progress)

def run_add() -> None:
    ap = argparse.ArgumentParser(description="Add an author's corpus or favorites to a mirror, or update them")  # noqa: E501
    ap.add_argument("-s", "--silent", action="store_true",
                    help="Suppress running output", default=False)
    ap.add_argument("-f", "--favorites", dest='ls', action="store_true",
                    default=False,
                    help="Get author's favorites rather than their corpus")
    ap.add_argument("-a", "--all", dest='getall', action="store_true",
                    default=False,
                    help="Download all stories without checking if already present")  # noqa: E501
    ap.add_argument("-d", "--dry-run", action="store_true", default=False,
                    help="Dry run (only parse list and print)")
    ap.add_argument("url", help="A URL for an author's profile")
    args = ap.parse_args()
    download_list(write_favs=True, **args.__dict__)

def update_mirror(silent=False, author=None) -> None:
    m = cur_mirror.read_entries()
    for n, i in enumerate(sorted(m.keys())):
        if author is not None and author != i:
            continue
        if not silent:
            print("Author '{}' (#{}/{})".format(m[i].info['author'], n + 1,
                                                len(m)))
        url = m[i].info['author_url']
        download_list(url, write_favs=True, silent=silent)

def run_update() -> None:
    ap = argparse.ArgumentParser(description="Update an entire mirror from the Web site")  # noqa: E501
    ap.add_argument("-s", "--silent", action="store_true",
                    help="Suppress running output", default=False)
    ap.add_argument("author", nargs='?', help="Update only a given author",
                    default=None)
    args = ap.parse_args()
    update_mirror(**args.__dict__)

def do_cache() -> None:
    cur_mirror.make_cache()

@click.group()
def run_db_op() -> None:
    pass

@run_db_op.command()
@click.option("-a", "--author-dir", type=str,
              help="Author directory to update", default=None)
@click.option("-m", "--max-authors", type=int,
              help="Maximum number of authors to update "
              "(to dodge Cloudflare rate-limiting)",
              default=None)
def update(author_dir: Optional[str], max_authors: Optional[int]) -> None:
    """Update the DB. If author-dir is given, update only that author."""
    mm = metadb.DBMirror('.')
    mm.connect()
    if author_dir is not None:
        dn = author_dir
        if dn.endswith('/'):
            dn = dn[:-1]
        site, aid = metadb.get_archive_id(dn)
        ao = mm.get_author(site, aid)
        mm.sync_author(ao)
        mm.archive_author(ao)
    else:
        mm.run_update(max_authors=max_authors)

@run_db_op.command()
@click.argument("url", type=str)
def add(url: str):
    """Add a new author to the DB."""
    mm = metadb.DBMirror('.')
    mm.connect()
    mod = parse_url(url)
    assert mod is not None
    site = mod.this_site
    o = mod.user_url_re.match(url)
    assert o is not None
    aid = o.group('aid')
    mm.sync_author((site, aid))
    ao = mm.get_author(site, aid)
    mm.archive_author(ao)

@run_db_op.command()
def init():
    """Initialize an ffmirror database in the current directory."""
    mm = metadb.DBMirror('.')
    mm.connect()
    mm.create()

@run_db_op.command()
def migrate():
    """Migrate from old versions of the DB to the latest version."""
    metadb.update_chapters(Path('.'))
