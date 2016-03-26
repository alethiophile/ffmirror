# Functions for parsing a mirror and serving HTML pages to navigate it, for use
# in CGI scripts. These functions use the cache created by ffmirror.mirror, but
# unconditionally, since ~1m delay in a CGI script is unacceptable. Make sure
# the cache is up to date for correct output.

#import ffmirror.mirror as mirror
import urllib.parse, pickle, sys
from datetime import datetime

page_thres = 100

def sort_authors(st):
    return sorted(iter(st.items()), key= lambda x: x[1][0]['author'].lower())

def format_number(n):
    if type(n) != str:
        n = str(n)
    if len(n) <= 3:
        return n
    return format_number(n[:-3]) + ',' + n[-3:]

def make_story_html(md, tags=True, author=False):
    """Takes a story metadata entry, writes out an HTML <li> for it. If tags is
    true, include a line with the story tags. If author is true, include a line
    with the author.

    """
    if tags:
        ts = ("&nbsp;" * 3).join("<a href=\"/tag.cgi?tag={0}\">{1}</a>".format(urllib.parse.quote(i), i) for i in sorted(md['tags'])) # This is convoluted.
    else:
        ts = None
    a = """<li class="story"><a href="{0}">{1}</a><br />
"""
    if author: a += """by {8}<br />
"""
    if tags: a += """<small><em>{2}</em></small><br />
"""
    a += """{3}<br />
Words: {4} — Chapters: {5} — Category: {6} — {11}{7}Published: {9} — Updated: {10}</li>
"""
    if 'genre' in md and md['genre']:
        gv = "{} — ".format(md['genre'])
    else:
        gv = ''
    chars = "Characters: {} — ".format(md['characters']) if md['characters'] else ''
    return a.format(md['filename'], md['title'], ts, md['summary'], format_number(md['words']), md['chapters'], md['category'], chars, md['author'], datetime.fromtimestamp(int(md['published'])).date().isoformat(), datetime.fromtimestamp(int(md['updated'])).date().isoformat(), gv)

def make_npls(page, last, tag=None):
    """Make HTML for next/previous links for the given page."""
    if tag == None:
        u = "index.cgi?"
    else:
        u = "tag.cgi?tag={}&".format(tag)
    if page == 0:
        pl = ""
    else:
        pl = """<div style="text-align: left; width=50%; float: left"><a href="{}page={}#liststart">&lt; Previous page</a></div>""".format(u, page - 1)
    if last:
        nl = ""
    else:
        nl = """<div style="text-align: right; width=50%; float: right"><a href="{}page={}#liststart">Next page &gt;</a></div>""".format(u, page + 1)
    return pl + nl + "<br />"

def write_index(outf, page, il, pages, tag=None):
    outs = "<ul>\n"
    for n, e in enumerate(il):
        a, sl = e
        for pn, pe in enumerate(pages):
            if n >= pe[0]:
                cp = pn
        if cp == page:
            ps = ""
        else:
            if tag == None:
                ps = "index.cgi?page={}".format(cp)
            else:
                ps = "tag.cgi?tag={}&page={}".format(tag, cp)
        outs += "<li><a href=\"{}#{}\">{} ({})</a></li>\n".format(ps, sl[0]['authorid'], sl[0]['author'], len(sl))
    outs += "</ul>\n"
    outf.write(outs)
    lb = make_npls(page, page == len(pages) - 1, tag)
    outf.write("<a name=\"liststart\" />\n")
    outf.write(lb + "\n")
    if page == -1:
        til = il
    else:
        til = il.__getitem__(slice(*pages[page]))
    for a, sl in til:
        sl.sort(key=lambda x: x['title'])
        sl.sort(key=lambda x: x['category'])
        aname = sl[0]['author']
        outs = "<h3><a name=\"{1}\">Stories by {0} (id {1})</a></h3>\n<ul>\n".format(aname, sl[0]['authorid'])
        for s in sl:
            outs += make_story_html(s)
        outs += "</ul>\n"
        outf.write(outs)
    outs = "{}\n</body>\n</html>\n".format(lb)
    outf.write(outs)

def write_main_index(outf, page=0):
    """Reads files under current directory for metadata, writes out an index file
    that kinda-sorta approximates the one you'd get from browsing FFnet.
    Includes tags data as read by read_entries, hence by read_tags. Reads the
    cache file 'index.db' as created by make_cache, so as to be fast enough to
    call in CGI. Make sure your cache is up to date.

    """
    with open('index.db', 'rb') as fcache:
        files = pickle.load(fcache)
    outs = """<html>
<head>
<meta charset="UTF-8">
<title>Index — {0} authors</title>
<style>
li.story {{ margin-bottom: 10px; }}
body {{ font-family: sans-serif; }}
</style>
</head>
<body>
<h2>Index of stories — {0} authors</h2>
""".format(len(list(files.keys())))
    outf.write(outs)
    il = sort_authors(files)
    write_index(outf, page, il, make_pages(il))

def write_tag_index(tag, outf, page=0):
    """Takes a tag name and a filename, writes out an index for the
    given tag to the filename."""
    with open("index.db", 'rb') as fcache:
        data = pickle.load(fcache)
    html = """<html>
<head>
<meta charset="UTF-8">
<title>Tag {0}</title>
<style>
li.story {{ margin-bottom: 10px; }}
body {{ font-family: sans-serif; }}
</style>
</head>
<body>
<h2>All stories with tag {0}</h2>
<a href="/">All stories</a>
""".format(tag)
    outf.write(html)
    il = sort_authors(data)
    il = [(n, [i for i in l if tag in i['tags']]) for n,l in il]
    il = [x for x in il if len(x[1]) != 0]
    write_index(outf, page, il, make_pages(il), tag)

def make_pages(il):
    cl = 0
    ol = []
    lc = 0
    for n,i in enumerate(il):
        cl += len(i[1])
        if cl >= page_thres:
            cl = 0
            ol.append((lc, n+1))
            lc = n+1
    if len(ol) == 0 or ol[-1][1] != len(il):
        ol.append((lc, len(il)))
    return ol
