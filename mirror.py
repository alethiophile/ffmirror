# Functions for maintaining an offline mirror of a large number of stories. The
# format of the mirror is as follows: in the top level are directories each
# titled for an author. Within each directory are files each titled for a story.
# Each file contains an entire story as HTML. The files contain comments with
# relevant metadata; this allows updating properly and browsing easily. The
# top-level directory also contains a single 'tags' file containing tags in the
# simpletags format; the resource is directory/file.html, while the tags are
# whatever.

import re, os, pickle, sys
import ffmirror.util as util
from ffmirror.simpletags import read_tags, write_tags

def story_file(md, with_id=False):
    if with_id:
        return os.path.join(util.make_filename(md['author']) + '-' + md['authorid'],
                            util.make_filename(md['title']) + '-' + md['id'] + '.html')
    else:
        return os.path.join(util.make_filename(md['author']), util.make_filename(md['title']) + '.html')

def cat_to_tagset(category):
    """Takes a category string, splits by crossover if necessary,
    returns a set of fandom tags for it. Uses the category_to_tag
    dictionary. This will mangle category names with the substring 
    ' & ' in them, but those are rare; I've seen only one ever."""
    rv = set()
    cl = category.split(' & ')
    for i in cl:
        # Tag name is category name, in lowercase, minus any commas
        rv.add(i.lower().replace(",", ""))
    return rv

def read_from_file(name):
    """Read a story metadata entry as returned by download_list out of
    a file. If file is nonexistent or unreadable, or metadata cannot
    be read, return None."""
    try:
        f = open(name, "rb", buffering=0) # Binary mode in order to support seek()
    except IOError:
        return None
    reading = False
    rv = {}
    for line in f:
        line = line.decode()
        if line[0:4] == "<!--" and not "-->" in line: # First (and presumably only) HTML comment in output file will be metadata block
            reading = True
            continue
        if reading:
            o = re.match(r"([^:]+): (.*)", line)
            if o:
                k,v = o.group(1),o.group(2)
                try:
                    if k in ['category', 'author', 'title']:
                        rv[k] = v
                    else:
                        rv[k] = int(v)
                except ValueError:
                    rv[k] = v
            else:
                break # End if we find a line that isn't metadata; this also triggers on finding the end comment
    if not reading:
        return None
    f.seek(-8, 2)
    s = f.readline().decode()
    if s != "</html>\n": # Incomplete file, probably left over from an earlier interrupted DL
        return None
    return rv

class FFMirror(object):
    def __init__(self, mirror_dir, use_ids=False):
        self.mirror_dir = mirror_dir
        self.use_ids = use_ids

    def check_update(self, r, n=None):
        """Check a downloaded metadata entry r against local files. Return
        true if this entry needs redownloading. Because some people
        (*cough*NeonZangetsu*cough*) can't pick unique titles for their
        stories, also return false if IDs are not the same. This means you
        miss one story or the other, but people who write multiple stories
        under the same title deserve what they get."""
        if n is None:
            n = os.path.join(self.mirror_dir, story_file(r, self.use_ids))
        cr = read_from_file(n)
        if cr == None:
            return True
        try:
            if r['id'] != cr['id'] and not self.use_ids:
                return False
            if r['words'] != cr['words'] or r['chapters'] != cr['chapters'] or r['updated'] != cr['updated']:
                return True
        except KeyError: # if the metadata is incomplete
            return True
        return False

    def update_list(self, sl, callback=None):
        """This function takes a list of stories (as metadata entries) and downloads
        them all. The filenames used are the result of story_file. No checking of
        update requirement is done; for update-only, the caller should filter on the
        result of check_update manually. callback is called at each story with the
        index and result of download_metadata for the current story; it is also
        passed to compile_story of the site module, which passes chapter index and
        string title.

        """
        for n, i in enumerate(sl):
            mod = util.unsilly_import("ffmirror." + i['site'])
            try:
                md, toc = mod.download_metadata(i['id'])
            except Exception as e:
                print(i)
                continue
            if callback: callback(n, (i, toc))
            fn = os.path.join(self.mirror_dir, story_file(i, self.use_ids))
            os.makedirs(os.path.split(fn)[0], exist_ok=True)
            with open(fn, 'w') as out:
                mod.compile_story(i, toc, out, contents=True, callback=callback)

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
            ct = cat_to_tagset(i['category'])
            if fn in to:
                to[fn].update(ct)
            else:
                to[fn] = ct
        write_tags(to, tfn)

    def read_entries(self):
        """Reads all the .html files below the current directory for ffmirror metadata;
        returns them as a dictionary of author name to list of story metadata
        entries. This should yield the data of all the files in the mirror. This
        function takes a long time on a large database; see the various caching
        functions.

        """
        rv = {}
        tfn = os.path.join(self.mirror_dir, 'tags')
        ts = read_tags(tfn)
        #print(ts, file=sys.stderr)
        for d, sds, fs in os.walk(self.mirror_dir):
            for n in fs:
                if n.endswith(".html"):
                    fn = os.path.join(d, n)
                    rel_fn = fn[len(self.mirror_dir)+1:] # path relative to mirror_dir
                    #print(fn, self.mirror_dir, rel_fn, file=sys.stderr)
                    a = read_from_file(fn)
                    if a == None:
                        continue
                    a['filename'] = rel_fn
                    if rel_fn in ts:
                        a['tags'] = ts[rel_fn]
                    else:
                        a['tags'] = set()
                    if a['author'] in rv:
                        rv[a['author']].append(a)
                    else:
                        rv[a['author']] = [a]
        return rv

    def make_cache(self):
        """Calls read_entries(), stores the result (pickled) in the file index.db. This
        takes a long time on a large database.

        """
        with open(os.path.join(self.mirror_dir, "index.db"), 'wb') as fcache:
            pickle.dump(self.read_entries(), fcache, 3)

    def get_index(self):
        """Checks if the cache created by make_cache is up to date; if not, updates it.
        Either way, returns the index dictionary created by read_entries()."""
        cache_fn = os.path.join(self.mirror_dir, "index.db")
        ls = max(((i, os.stat(os.path.join(self.mirror_dir, i))) for i in os.listdir(self.mirror_dir)), key=lambda x: x[1].st_mtime)
        if ls[0] != "index.db":
            a = self.read_entries()
            with open(cache_fn, 'wb') as fcache:
                pickle.dump(a, fcache, 3)
        else:
            with open(cache_fn, 'rb') as fcache:
                a = pickle.load(fcache)
        return a
