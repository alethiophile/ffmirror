#!/usr/bin/python3

# API docs
# Download-story functions
# Take an ID; URL parsing is out-of-scope
# Write to a provided file-like object; opening is out-of-scope
# Take formatting options; a bit ugly, but can't think of a better option
# Get-metadata functions
# Also deals with table of contents
# Parse-author functions

import urllib.request, urllib.error, re
from bs4 import BeautifulSoup

from ffmirror.util import *

hostname = "www.fanfiction.net"
story_url = "http://{hostname}/s/{number}/{chapter}/"
user_url = "http://{hostname}/u/{number}/"

story_url_re = re.compile(r"https?://[^/]+/s/(?P<number>\d+)/?(?P<chapter>\d+)?/?")
user_url_re = re.compile(r"https?://[^/]+/u/(?P<number>\d+)/?")

def get_contents(soup):
    """Given a BeautifulSoup of a story page, extract the contents list and
    return list of chapter titles."""
    e = soup.find("table", cellpadding="5")
    se = e.find("select")
    if se == None:
        return ['Chapter 1'] # it's a oneshot, so no chapter list
    rv = []
    for oe in se.find_all('option'):
        val = re.match(r"\d+. (.+)", oe.string).group(1)
        rv.append(val)
    return rv

# Apparently souping the storytext can mess some things up when FFn uses bad HTML.
# def get_storytext(soup):
#     """Takes a soup of the page, extracts the story text HTML and returns it."""
#     st = soup.find('div', id='storytext')
#     d = str(st)
#     d = re.sub(r"^<div[^>]*>", "", d)
#     d = re.sub(r"</div>$", "", d)
#     return d

def get_storytext(d):
    """Takes a page of HTML, extracts the storytext, returns it."""
    o = re.search("<div[^>]*id='storytext'[^>]*>", d)
    if o == None:
        raise Exception("Didn't find storytext")
    d = d[o.end():]
    o = re.search("</div>", d)
    if o == None:
        raise Exception("Didn't find storytext end")
    d = d[:o.start()]
    return d

def get_metadata(soup):
    """Given a BeautifulSoup of an FFnet page, extract a metadata
    entry. Somewhat abbreviated from what download_list returns, since it's
    parsing rendered HTML rather than JS, and some information is lost."""
    e = soup.find("table", cellpadding="5")
    td = e.find("td")
    title = td.find("b").string
    ae = td.find("a")
    author = ae.string
    authorid = re.match(r"/u/(\d+)/.*", ae['href']).group(1)
    sd = td.find("div", class_='xcontrast_txt')
    summary = sd.string
    md = sd.find_next_sibling("span", class_='xcontrast_txt')
    s = md.a.next_sibling
    o = re.match(r"[ -]+\w+[ -]+([\w/]+ - )?((?P<chars>(?!Chapters).*?\S) +- +)?(Chapters: (?P<chaps>\d+)[ -]+)?Words: (?P<words>[\d,]+).*", s)
    characters = o.group('chars')
    if characters == None:
        characters = ""
    try:
        chapters = int(o.group('chaps'))
    except TypeError:
        chapters = 1
    words = int(o.group('words').replace(",", ""))
    ae = md.a.find_next_sibling('a')
    if ae == None:
        reviews = 0
        ids = s
    else:
        reviews = int(ae.string.replace(",", ""))
        ids = ae.next_sibling
    sid = re.match(r".*id: (\d+).*", ids).group(1)
    e = soup.find("div", id='pre_story_links')
    try:
        category = e.a.find_next_sibling('a').string
    except AttributeError:
        category = 'crossover'
    return {'title': title, 'summary': summary, 'category': category, 'id': sid, 'reviews': reviews, 'chapters': chapters, 'words': words, 'characters': characters, 'source': 'story', 'author': author, 'authorid': authorid, 'site': 'ffnet'}

def make_toc(contents):
    """Makes an HTML string table of contents to be concatenated into outstr, given the return value
    of get_contents (array of chapter names)."""
    rs = "<h2>Contents</h2>\n<ol>\n"
    for x in range(len(contents)):
        n = x + 1
        anc = "#ch{}".format(n)
        rs += "<li><a href=\"{}\">{}</a></li>\n".format(anc, contents[x])
    rs += "</ol>\n"
    return rs

def download_metadata(number):
    """This function takes a fic number and returns a pair: the first is a
    dictionary of the story's metadata, the second is sufficient information to
    download all its individual chapters.

    """
    url = story_url.format(hostname=hostname, number=number, chapter=1)
    r = urlopen_retry(url)
    data = r.read()
    soup = BeautifulSoup(data)
    md = get_metadata(soup)
    toc = get_contents(soup)
    return md, toc

def compile_story(md, toc, outfile, headers=True, contents=False, kindle=False, callback=None, **kwargs):
    outfile.write("""<html>
<head>
<meta charset="UTF-8">
<title>{}</title>
<style type="text/css">
body {{ font-family: sans-serif }}
</style>
</head>
<!-- Fic ID: {}
""".format(md['title'], md['id']))
    for k,v in md.items():
        outfile.write("{}: {}\n".format(k,v))
    outfile.write("-->\n<body>\n")
    if headers:
        outfile.write("<h1>{}</h1>\n".format(md['title']))
    if contents:
        outfile.write(make_toc(toc))
    for n, t in enumerate(toc):
        x = n + 1
        url = story_url.format(hostname=hostname, number=md['id'], chapter=x)
        if callback: # For printing progress as it runs.
            callback(n,t)
        r = urlopen_retry(url)
        data = r.read().decode()
        text = get_storytext(data)
        if headers:
            outfile.write("""<h2 id="ch{}">{}</h2>\n""".format(x, t))
        if kindle:
            text = re.sub(r'\<hr[^>]+\>', '<p>* * *</p>', text)
        text = fold_string_indiscriminately(text)
        outfile.write(text + "\n\n")
    outfile.write("</body>\n</html>\n")
