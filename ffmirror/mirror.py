# Functions for maintaining an offline mirror of a large number of stories. The
# format of the mirror is as follows: in the top level are directories each
# titled for an author. Within each directory are files each titled for a
# story. Each file contains an entire story as HTML. The files contain comments
# with relevant metadata; this allows updating properly and browsing easily.
# The top-level directory also contains a single 'tags' file containing tags in
# the simpletags format; the resource is directory/file.html, while the tags
# are whatever.

import os, pickle, traceback, json
import ffmirror.util as util
from ffmirror.simpletags import read_tags, write_tags
from .core import StoryInfo
from typing import Optional, Dict, Any
from datetime import datetime
from . import site_modules as sites

def story_file(md: StoryInfo, with_id: bool = False) -> str:
    if with_id:
        return os.path.join(
            "{}-{}-{}".format(util.make_filename(md.author.name),
                              md.site, md.author.id),
            util.make_filename("{}-{}.html".format(md.title,
                                                   md.id)))
    else:
        return os.path.join(util.make_filename(md.author.name),
                            util.make_filename(md.title) + '.html')

def read_from_file(name: str) -> Optional[StoryInfo]:
    """Read a story metadata entry as returned by download_list out of
    a file. If file is nonexistent or unreadable, or metadata cannot
    be read, return None."""
    try:
        # Binary mode in order to support seek()
        f = open(name, "rb", buffering=0)
    except IOError:
        return None
    reading = False
    rv: Dict[str, Any] = {}
    for bline in f:
        line = bline.decode()
        # First (and presumably only) HTML comment in output file will be
        # metadata block
        if line[0:4] == "<!--" and "-->" not in line:
            reading = True
            continue
        if reading:
            try:
                k, v = line.strip("\n").split(': ', 1)
            except ValueError:
                break
            if k in ['published', 'updated']:
                try:
                    rv[k] = datetime.fromtimestamp(int(v))
                except ValueError:
                    rv[k] = datetime.fromisoformat(v)
            else:
                rv[k] = v
    if not reading:
        return None
    f.seek(-8, 2)
    s = f.readline().decode()
    # Incomplete file, probably left over from an earlier interrupted DL
    if s != "</html>\n":
        return None
    return StoryInfo.from_dict(rv)

# Turns out the optimized-and-kind-of-painful version really is about twice as
# fast as brute-force, which I think is worth it.

class AuthorInfo(object):
    def __init__(self, author_dir):
        self.stories = []
        self._info = None
        self._favs = None
        self._author_dir = author_dir

    @property
    def info(self):
        if self._info is not None:
            return self._info
        test = self.favs  # noqa: F841 (this is a hack)
        return self._info

    @property
    def favs(self):
        if self._favs is not None:
            return self._favs
        fn = os.path.join(self._author_dir, 'favorites.json')
        try:
            with open(fn) as inp:
                ai = json.load(inp)
        except:
            return []
        if self._info is None:
            self._info = ai['info']
        self._favs = ai['favs']
        return self._favs

    def with_tag(self, tag):
        rv = AuthorInfo(self._author_dir)
        rv.stories = [i for i in self.stories if tag in i['tags']]
        rv._info, rv._favs = self._info, self._favs
        if len(rv.stories) == 0:
            return None
        return rv

class FFMirror(object):
    def __init__(self, mirror_dir, use_ids=True):
        self.mirror_dir = mirror_dir
        self.use_ids = use_ids

    def check_update(self, r: StoryInfo, n: Optional[str] = None) -> bool:
        """Check a downloaded metadata entry r against local files. Return true if this
        entry needs redownloading. This will return false (thus failing) on
        colliding story titles if and only if use_ids is turned off. It is
        recommended to set use_ids to on.

        """
        if n is None:
            n = os.path.join(self.mirror_dir, story_file(r, self.use_ids))
        cr = read_from_file(n)
        if cr is None:
            return True
        # mod = sites[r.site]
        return not r == cr

    def update_list(self, sl, callback=None):
        """This function takes a list of stories (as metadata entries) and downloads
        them all. The filenames used are the result of story_file. No checking
        of update requirement is done; for update-only, the caller should
        filter on the result of check_update manually. callback is called at
        each story with the index and result of download_metadata for the
        current story; it is also passed to compile_story of the site module,
        which passes chapter index and string title.

        """
        for n, i in enumerate(sl):
            mod = sites[i['site']]
            try:
                md, toc = mod.download_metadata(i['id'])
            except Exception as e:
                print(i)
                traceback.print_exc()
                continue
            if callback:
                callback(n, (i, toc))
            fn = os.path.join(self.mirror_dir, story_file(md, self.use_ids))
            os.makedirs(os.path.split(fn)[0], exist_ok=True)
            with open(fn, 'w') as out:
                mod.compile_story(md, toc, out, contents=True,
                                  callback=callback)

    def update_tags(self, sl):
        """This function takes a list of metadata entries and updates the category tag
        on all of them. The result of cat_to_tagset on each story's category is
        added to that story's tag set; tags are then written back.

        """
        tfn = os.path.join(self.mirror_dir, 'tags')
        try:
            to = read_tags(tfn)
        except FileNotFoundError:
            to = {}
        for i in sl:
            fn = story_file(i, self.use_ids)
            mod = sites[i['site']]
            ct = mod.get_tags_for(i)
            if fn in to:
                to[fn].update(ct)
            else:
                to[fn] = ct
        write_tags(to, tfn)

    def read_entries(self):
        """Reads all the .html files below the current directory for ffmirror metadata;
        returns them as a dictionary of author name to list of story metadata
        entries. This should yield the data of all the files in the mirror.
        This function takes a long time on a large database; see the various
        caching functions.

        """
        rv = {}
        tfn = os.path.join(self.mirror_dir, 'tags')
        try:
            ts = read_tags(tfn)
        except FileNotFoundError:
            ts = {}
        for d, sds, fs in os.walk(self.mirror_dir):
            for i in [n for n in sds if n.startswith('.')]:
                sds.remove(i)
            for n in fs:
                if n.endswith(".html"):
                    fn = os.path.join(d, n)
                    rel_fn = os.path.relpath(fn, self.mirror_dir)
                    a = read_from_file(fn)
                    if a is None:
                        continue
                    a['filename'] = rel_fn
                    adn = os.path.dirname(rel_fn)
                    if rel_fn in ts:
                        a['tags'] = ts[rel_fn]
                    else:
                        a['tags'] = set()
                    if adn in rv:
                        rv[adn].stories.append(a)
                    else:
                        rv[adn] = AuthorInfo(os.path.abspath(
                            os.path.dirname(fn)))
                        rv[adn].stories.append(a)
        return rv

    def make_cache(self):
        """Calls read_entries(), stores the result (pickled) in the file index.db. This
        takes a long time on a large database.

        """
        with open(os.path.join(self.mirror_dir, "index.db"), 'wb') as fcache:
            pickle.dump(self.read_entries(), fcache, 3)

    def get_index(self, check=True):
        """Checks if the cache created by make_cache is up to date; if not, updates it.
        Either way, returns the index dictionary created by read_entries(). If
        check is false, return the cache unconditionally (used in the Web app).

        """
        cache_fn = os.path.join(self.mirror_dir, "index.db")
        ls = max(((i, os.stat(os.path.join(self.mirror_dir, i))) for i in
                  os.listdir(self.mirror_dir)), key=lambda x: x[1].st_mtime)
        if check and ls[0] != "index.db":
            a = self.read_entries()
            with open(cache_fn, 'wb') as fcache:
                pickle.dump(a, fcache, 3)
        else:
            with open(cache_fn, 'rb') as fcache:
                a = pickle.load(fcache)
        return a
