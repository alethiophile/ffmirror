# Functions for maintaining an offline mirror of a large number of stories. The
# format of the mirror is as follows: in the top level are directories each
# titled for an author. Within each directory are files each titled for a story.
# Each file contains an entire story as HTML. The files contain comments with
# relevant metadata; this allows updating properly and browsing easily. The
# top-level directory also contains a single 'tags' file containing tags in the
# simpletags format; the resource is directory/file.html, while the tags are
# whatever.

import re, os, pickle
import ffmirror.util as util
from simpletags import read_tags, write_tags

# A dictionary mapping FFnet's idea of category to a tag name I can
# use for my system. The default is to simply lowercase the category
# name and strip commas from it; entries shouldn't be added unless the
# desired tag is different from that result.
category_to_tag = { 'Avatar: Last Airbender': 'avatar',
                    'Familiar of Zero': 'zero no tsukaima',
                    'Dragon Ball Z': 'dbz',
                    'Terminator: Sarah Connor Chronicles': 'sarah connor chronicles',
                    'My Little Pony': 'mlp',
                    'Warhammer': 'wh40k',
                    'Oh My Goddess!': 'ah my goddess',
                    'House, M.D.': 'house md',
                    'Haruhi Suzumiya series': 'haruhi',
                    'Higurashi/Umineko series': 'higurashi',
                    'Rosario + Vampire': 'rosario to vampire',
#                    'Negima! Magister Negi Magi/魔法先生ネギま！': 'negima',
#                    'Puella Magi Madoka Magica/魔法少女まどか★マギカ': 'madoka',
#                    "My Little Sister Can't Be This Cute/俺の妹がこんなに可愛いわけがない": 'ore no imouto',
#                    'Toaru Majutsu no Index/とある魔術の禁書目録': 'toaru majutsu',
#                    'Sword Art Online/ソードアート・オンライン': 'sao',
#                    'Medaka Box/めだかボックス': 'medaka box',
#                    'Bakemonogatari/化物語': 'bakemonogatari',
#                    'Girls und Panzer/ガールズ&パンツァー': 'girls und panzer',
#                    'Infinite Stratos/IS<インフィニット・ストラトス>': 'infinite stratos',
                    }

def story_file(md):
    return os.path.join(util.make_filename(md['author']), util.make_filename(md['title']) + '.html')

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
                    rv[k] = int(v)
                except ValueError:
                    rv[k] = v
                if k == 'category':
                    rv[k] = str(rv[k]) # a hack, but this should always be a string and sometimes isn't (work title '1776', I'm looking at you)
            else:
                break # End if we find a line that isn't metadata; this also triggers on finding the end comment
    if not reading:
        return None
    f.seek(-8, 2)
    s = f.readline().decode()
    if s != "</html>\n": # Incomplete file, probably left over from an earlier interrupted DL
        return None
    return rv

def check_update(r):
    """Check a downloaded metadata entry r against local files. Return
    true if this entry needs redownloading. Because some people
    (*cough*NeonZangetsu*cough*) can't pick unique titles for their
    stories, also return false if IDs are not the same. This means you
    miss one story or the other, but people who write multiple stories
    under the same title deserve what they get."""
    n = story_file(r)
    cr = read_from_file(n)
    if cr == None:
        return True
    try:
        if r['id'] != cr['id']:
            return False
        if r['words'] != cr['words'] or r['chapters'] != cr['chapters'] or r['updated'] != cr['updated']:
            return True
    except KeyError: # if the metadata is incomplete
        return True
    return False

def cat_to_tagset(category):
    """Takes a category string, splits by crossover if necessary,
    returns a set of fandom tags for it. Uses the category_to_tag
    dictionary. This will mangle category names with the substring 
    ' & ' in them, but those are rare; I've seen only one ever."""
    rv = set()
    cl = category.split(' & ')
    for i in cl:
        try:
            rv.add(category_to_tag[i])
        except KeyError:
            rv.add(i.lower().replace(",", "")) # If a thing isn't in the list, just use its name in lowercase as a default,
                                               # stripping out commas which are special to the tagging system
    return rv

def update_list(sl, callback=None):
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
        n = story_file(i)
        os.makedirs(os.path.split(n)[0], exist_ok=True)
        with open(n, 'w') as out:
            mod.compile_story(i, toc, out, contents=True, callback=callback)

def update_tags(sl):
    """This function takes a list of metadata entries and updates the category tag
    on all of them. The result of cat_to_tagset on each story's category is
    added to that story's tag set; tags are then written back.

    """
    try:
        to = read_tags()
    except FileNotFoundError:
        to = {}
    for i in sl:
        fn = story_file(i)
        ct = cat_to_tagset(i['category'])
        if fn in to:
            to[fn].update(ct)
        else:
            to[fn] = ct
    write_tags(to)

def read_entries():
    """Reads all the .html files below the current directory for ffmirror metadata;
    returns them as a dictionary of author name to list of story metadata
    entries. This should yield the data of all the files in the mirror. This
    function takes a long time on a large database; see the various caching
    functions.

    """
    rv = {}
    ts = read_tags()
    for d, sds, fs in os.walk("."):
        for n in fs:
            if n.endswith(".html"):
                fn = os.path.join(d, n)[2:] # elide './' from front
                a = read_from_file(fn)
                if a == None:
                    continue
                a['filename'] = fn
                if fn in ts:
                    a['tags'] = ts[fn]
                else:
                    a['tags'] = set()
                if a['author'] in rv:
                    rv[a['author']].append(a)
                else:
                    rv[a['author']] = [a]
    return rv

def make_cache():
    """Calls read_entries(), stores the result (pickled) in the file index.db. This
    takes a long time on a large database.

    """
    with open("index.db", 'wb') as fcache:
        pickle.dump(read_entries(), fcache, 3)

def get_index():
    """Checks if the cache created by make_cache is up to date; if not, updates it.
    Either way, returns the index dictionary created by read_entries()."""
    ls = max(((i, os.stat(i)) for i in os.listdir()), key=lambda x: x[1].st_mtime)
    if ls[0] != "index.db":
        a = read_entries()
        with open("index.db", 'wb') as fcache:
            pickle.dump(a, fcache, 3)
    else:
        with open("index.db", 'rb') as fcache:
            a = pickle.load(fcache)
    return a
