#!/usr/bin/python

# This is a simple tagging system, originally part of the offline-dump
# maintainer of ffnet_scraper. Keeps tags in a text file, with a
# single entry per line, in the format '<resource>:
# <tag>[,<tag>,<tag>]'. Deals with tags objects which take the form of
# dictionaries from string resource to set of tags.

def read_tags(fn='tags'):
    """Reads a file containing tags, in the format 'resource:
    tag1,tag2,tag3' per line. Returns a dictionary of string to set of
    tags. If a resource shows up multiple times, just add all the tags
    in all appearances to one set. Tags may contain anything that
    isn't a comma, including whitespace; resources may contain
    anything that isn't a colon, but in practice are only ever
    alphanumeric plus [/_.]. The resource can be any string; in
    practice it's usually a filename for something."""
    if type(fn) == str:
        data = open(fn, "r")
    elif type(fn) == file:
        data = fn
    else:
        raise Exception("Invalid argument")
    d = {}
    for l in data:
        l = l[:-1] # clip newline
        i = l.find(": ")
        n, t = l.split(": ", 1)
        ts = [i for i in t.split(',') if len(i) > 0]
        if n in d:
            d[n].update(ts)
        else:
            d[n] = set(ts)
    return d

def get_tagset(tags):
    """Takes a tags object as returned by read_tags, returns a set of
    all tags used in the database."""
    s = set()
    for i in tags:
        s.update(tags[i])
    return s

def _extract_tobj(sobj):
    """Takes a list-of-stories dictionary as returned by read_entries,
    returns a tags object suitable for write_tags, by rebuilding the
    dictionary. This is a holdover from functionality in
    ffnet_scraper; it shouldn't be used in a tagging system."""
    rv = {}
    if type(sobj) == dict: # it's a straight RV dictionary
        for a, l in sobj.iteritems():
            for c in l:
                rv[c['filename']] = c['tags']
    elif type(sobj) == list: # it's a list of metadatas, more convenient to munge
        for c in sobj:
            rv[c['filename']] = c['tags']
    else:
        raise Exception("Invalid argument")
    return rv

def write_tags(tags, fn='tags'):
    """Writes a tags object (dictionary of sets, as the return value
    of read_tags() above) into the file tags."""
    if type(fn) == str:
        f = open(fn, "w")
    elif type(fn) == file:
        f = fn
    else:
        raise Exception("Invalid argument")
    for l in sorted(tags.keys()):
        f.write("{}: {}\n".format(l, ",".join(sorted(tags[l]))))
    if type(fn) == str:
        f.close()

def list_for_tag(tags, tag):
    """Takes a tags object as returned by read_tags and a tag name,
    returns a set of all the resources which have that tag."""
    rv = set()
    for f in tags.keys():
        if tag in tags[f]:
            rv.add(f)
    return rv
