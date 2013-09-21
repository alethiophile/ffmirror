# This is the site module for FF.net, and the model for other site modules. It
# handles only FF.net-specific tasks; the API provided includes
# download_metadata, compile_story, and download_list. The functions can be
# called on their own, but it's probably friendlier to use the runner in
# __main__ or the update functions in mirror.

import urllib.request, urllib.error, re, shlex
import http.cookiejar
from bs4 import BeautifulSoup

from ffmirror.util import *

hostname = "www.fanfiction.net"
story_url = "http://www.fanfiction.net/s/{number}/{chapter}/"
user_url = "http://www.fanfiction.net/u/{number}/"

story_url_re = re.compile(r"https?://[^/]+/s/(?P<number>\d+)/?(?P<chapter>\d+)?/?")
user_url_re = re.compile(r"https?://[^/]+/u/(?P<number>\d+)/?")

# Functions related to downloading stories

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
    url = story_url.format(number=number, chapter=1)
    r = urlopen_retry(url)
    data = r.read()
    soup = BeautifulSoup(data)
    md = get_metadata(soup)
    toc = get_contents(soup)
    return md, toc

def compile_story(md, toc, outfile, headers=True, contents=False, kindle=False, callback=None, **kwargs):
    """Given the output of download_metadata, download all chapters of a story and
    write them to outfile. Extra keyword arguments are ignored in order to
    facilitate calls. callback is called as each chapter is downloaded with the
    chapter index and title; this should be a quick function to print progress
    output or similar.

    """
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
        url = story_url.format(number=md['id'], chapter=x)
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

# Functions related to dealing with user listings

def parse_entry(ent):
    """Takes the Javascript function in the page source that populates
    the story entry, and extracts various relevant information from
    it. Returns a dictionary."""
    o = re.match(r"story_set\((.+)\);", ent)
    if not o:
        raise Exception("Invalid entry {}".format(ent))
    d = o.group(1) # This is the stuff inside the parentheses
    s = shlex.shlex(d, posix=True) # Parse by tokens, respecting quoted strings
    s.whitespace += ',' # Split on commas
    s.escapedquotes += "'" # Respect escaped apostrophes inside single-quoted strings
    l = list(s)
    item = {}
    item['title'] = l[1]
    item['summary'] = l[3].replace('\\"', '"') # For some reason, the JS strings escape double quotes even in single-quoted strings. 
    item['category'] = l[7]
    item['id'] = int(l[8])
    item['published'] = int(l[11])
    item['updated'] = int(l[14])
    item['reviews'] = int(l[17])
    item['chapters'] = int(l[18])
    item['words'] = int(l[21])
    item['characters'] = l[25]
    if l[0] == 'fs_array':
        item['source'] = 'favorites'
        item['author'] = l[5]
        item['authorid'] = int(l[4])
    elif l[0] == 'st_array':
        item['source'] = 'authored'
        item['author'] = ''
        item['authorid'] = 0
    item['site'] = 'ffnet'
    return item

def download_list(number):
    """Given a user ID, download lists of the stories they've written and favorited
    and return them. The lists are returned as a tuple of (authored, faved).
    Each entry is a dictionary containing metadata.

    """
    url = user_url.format(number=number)
    r = urlopen_retry(url)
    page = r.read().decode()
    o = re.search(r"<title>(.+) \| FanFiction</title>", page)
    if not o:
        raise Exception("Couldn't find author name for {}".format(number))
    aname = o.group(1)
    l = [parse_entry(i) for i in re.findall(r"story_set\(.+?\);", page)]
    ra = []
    rf = []
    for i in l:
        if i['source'] == 'authored':
            i['author'] = aname
            i['authorid'] = number
            ra.append(i)
        elif i['source'] == 'favorites':
            rf.append(i)
    return ra, rf
