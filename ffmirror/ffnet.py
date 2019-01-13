# This is the site module for FF.net, and the model for other site modules. It
# handles only FF.net-specific tasks; the API provided includes
# download_metadata, compile_story, and download_list. The functions can be
# called on their own, but it's probably friendlier to use the runner in
# __main__ or the update functions in mirror. Also handles FictionPress, since
# they're identical.

import re, time
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString

from ffmirror.util import (make_filename, urlopen_retry,
                           fold_string_indiscriminately)

def cat_to_tagset(category):
    """Takes a category string, splits by crossover if necessary, returns a set of
    fandom tags for it. This will mangle category names with the substring
    ' & ' in them, but those are rare; I've seen only one ever.

    """
    rv = set()
    cl = category.split(' & ')
    for i in cl:
        # Tag name is category name, in lowercase, minus any commas
        rv.add(i.lower().replace(",", ""))
    return rv

# A site module needs to implement the following:
#  - get_user_url(self, md):
#    given a story metadata object, return a canonical link for the author
#  - get_story_url(self, md):
#    given a story metadata object, return a canonical link for the story
#  - download_metadata(self, sid):
#    given a story ID, download its metadata and TOC and return
#  - compile_story(self, md, toc, outfile):
#    given metadata and TOC, download a whole story and write it to outfile
#  - download_list(self, aid):
#    given author ID, download a list of stories as metadata (metadata entries
#    may be incomplete)
class FFNet(object):
    hostname = "www.fanfiction.net"
    this_site = "ffnet"
    story_url = "https://{hostname}/s/{number}/{chapter}/"
    user_url = "https://{hostname}/u/{number}/"

    file_version = 3  # for metadata check

    story_url_re = re.compile(r"https?://(?P<hostname>[^/]+)/s/(?P<sid>\d+)/?(?P<chl>\d+)?/?")  # noqa: E501
    user_url_re = re.compile(r"https?://(?P<hostname>[^/]+)/u/(?P<aid>\d+)/?")

    def get_user_url(self, md):
        return self.user_url.format(number=md['authorid'],
                                    hostname=self.hostname)

    def get_story_url(self, md):
        return self.story_url.format(number=md['id'], chapter=1,
                                     hostname=self.hostname)

    # Functions related to downloading stories

    def _get_contents(self, soup):
        """Given a BeautifulSoup of a story page, extract the contents list and
        return list of chapter titles."""
        se = soup.find("select", id="chap_select")
        if se is None:
            return ['Chapter 1']  # it's a oneshot, so no chapter list
        rv = []
        for oe in se.find_all('option'):
            val = re.match(r"\d+. (.*)", oe.string).group(1)
            rv.append(val)
        return rv

    # Apparently souping the storytext can mess some things up when FFn uses
    # bad HTML.

    # def get_storytext(soup):
    #     """Takes a soup of the page, extracts the story text HTML and returns
    #     it."""
    #     st = soup.find('div', id='storytext')
    #     d = str(st)
    #     d = re.sub(r"^<div[^>]*>", "", d)
    #     d = re.sub(r"</div>$", "", d)
    #     return d

    def _get_storytext(self, d):
        """Takes a page of HTML, extracts the storytext, returns it."""
        o = re.search("<div[^>]*id='storytext'[^>]*>", d)
        if o is None:
            raise Exception("Didn't find storytext")
        d = d[o.end():]
        o = re.search("</div>", d)
        if o is None:
            raise Exception("Didn't find storytext end")
        d = d[:o.start()]
        return d

    def _get_metadata(self, soup):
        """Given a BeautifulSoup of an FFnet page, extract a metadata entry. Somewhat
        abbreviated from what download_list returns, since it's parsing
        rendered HTML rather than JS, and some information is lost. This
        function need change often to handle FFnet's constant dumb alterations;
        I wish they'd provide an API.

        """
        e = soup.find("div", id="profile_top")
        title = e.find("b").string
        ae = e.find("a")
        author = ae.string
        authorid = re.match(r"/u/(\d+)/.*", ae['href']).group(1)
        sd = e.find("div", class_='xcontrast_txt')
        summary = sd.string
        md = sd.find_next_sibling("span", class_='xcontrast_txt')
        s = md.a.next_sibling
        o = re.match(r"[ -]+\w+[ -]+((?P<genre>[\w/]+) - )?((?P<chars>(?!Chapters).*?\S) +- +)?(Chapters: (?P<chaps>\d+)[ -]+)?Words: (?P<words>[\d,]+).*", s)  # noqa: E501
        characters = o.group('chars')
        genre = o.group('genre') or ''
        if characters is None:
            characters = ""
        try:
            chapters = int(o.group('chaps'))
        except TypeError:
            chapters = 1
        words = int(o.group('words').replace(",", ""))
        ae = md.a.find_next_sibling('a')
        if ae is None:
            reviews = 0
            ids = s
        else:
            reviews = int(ae.string.replace(",", ""))
            ids = ae.next_sibling
        ids = md.get_text()
        sid = re.match(r".*id: (\d+).*", ids).group(1)
        ud = md.find("span", attrs={"data-xutime": True})
        if ud.previous_sibling.endswith("Updated: "):
            updated = int(ud['data-xutime'])
            pd = ud.find_next_sibling("span", attrs={"data-xutime": True})
            published = int(pd['data-xutime'])
        elif ud.previous_sibling.endswith("Published: "):
            published = int(ud['data-xutime'])
            updated = published
        complete = 'Status: Complete' in md.get_text()
        e = soup.find("div", id='pre_story_links')
        try:
            category = e.a.find_next_sibling('a').string
        except AttributeError:
            category = 'crossover'
        author_url = self.user_url.format(hostname=self.hostname,
                                          number=authorid)
        story_url = self.story_url.format(hostname=self.hostname, number=sid,
                                          chapter=1)
        author_dir = "{}-{}-{}".format(make_filename(author), self.this_site,
                                       authorid)
        trv = {'title': title, 'summary': summary, 'category': category,
               'id': sid, 'reviews': reviews, 'chapters': chapters,
               'words': words, 'characters': characters, 'source': 'story',
               'author': author, 'authorid': authorid, 'genre': genre, 'site':
               self.this_site, 'updated': updated, 'published': published,
               'complete': complete, 'story_url': story_url, 'author_url':
               author_url, 'author_dir': author_dir}
        for i in trv:
            if type(trv[i]) == NavigableString:
                trv[i] = str(trv[i])
        return trv

    def _make_toc(self, contents):
        """Makes an HTML string table of contents to be concatenated into outstr, given
        the return value of _get_contents (array of chapter names).

        """
        rs = "<h2>Contents</h2>\n<ol>\n"
        for x in range(len(contents)):
            n = x + 1
            anc = "#ch{}".format(n)
            rs += "<li><a href=\"{}\">{}</a></li>\n".format(anc, contents[x])
        rs += "</ol>\n"
        return rs

    def download_metadata(self, number):
        """This function takes a fic number and returns a pair: the first is a
        dictionary of the story's metadata, the second is sufficient
        information to download all its individual chapters.

        """
        url = self.story_url.format(hostname=self.hostname, number=number,
                                    chapter=1)
        r = urlopen_retry(url)
        data = r.read()
        soup = BeautifulSoup(data, 'html5lib')
        md = self._get_metadata(soup)
        toc = self._get_contents(soup)
        return md, toc

    def compile_story(self, md, toc, outfile, headers=True, contents=False,
                      kindle=False, callback=None, **kwargs):
        """Given the output of download_metadata, download all chapters of a story and
        write them to outfile. Extra keyword arguments are ignored in order to
        facilitate calls. callback is called as each chapter is downloaded with
        the chapter index and title; this should be a quick function to print
        progress output or similar, since its completion blocks continuing the
        download.

        """
        outfile.write("""<html>
<head>
<meta charset="UTF-8" />
<meta name="Author" content="{author}" />
<title>{title}</title>
<style type="text/css">
body {{ font-family: sans-serif }}
</style>
</head>
<!-- Fic ID: {id}
""".format(title=md['title'], id=md['id'], author=md['author']))
        for k, v in sorted(md.items()):
            outfile.write("{}: {}\n".format(k, v))
        outfile.write("-->\n<body>\n")
        if headers:
            outfile.write("<h1>{}</h1>\n".format(md['title']))
        if contents:
            outfile.write(self._make_toc(toc))
        for n, t in enumerate(toc):
            time.sleep(2)
            x = n + 1
            url = self.story_url.format(hostname=self.hostname,
                                        number=md['id'], chapter=x)
            if callback:  # For printing progress as it runs.
                callback(n, t)
            r = urlopen_retry(url)
            data = r.read().decode()
            text = self._get_storytext(data)
            if headers:
                outfile.write("""<h2 id="ch{}" class="chapter">{}</h2>\n""".
                              format(x, t))
            if kindle:
                text = re.sub(r'\<hr[^>]+\>', '<p>* * *</p>', text)
            text = fold_string_indiscriminately(text)
            outfile.write(text + "\n\n")
        outfile.write("</body>\n</html>\n")

    # Functions related to dealing with user listings

    def _parse_entry(self, elem):
        """Given a BeautifulSoup element for a story listing, return a metadata object
        for the story.

        """
        title = elem['data-title'].replace("\\'", "'")
        category = elem['data-category'].replace("\\'", "'")
        sid = elem['data-storyid']
        published = int(elem['data-datesubmit'])
        updated = int(elem['data-dateupdate'])
        reviews = int(elem['data-ratingtimes'])
        chapters = int(elem['data-chapters'])
        words = int(elem['data-wordcount'])
        sd = elem.find('div')
        summary = sd.contents[0]
        sd = sd.find('div')
        o = re.match(r"(Crossover - )?(?P<category>.+?) - Rated: (?P<rating>.{1,2}) - (?P<language>.+?) - (?P<genre>.+?) - ", sd.contents[0])  # noqa: E501
        genre = o.group('genre')
        if 'Chapters' in genre:
            genre = ''
        cs = sd.contents[-1]
        if type(cs) == Tag:
            chars = ''
        else:
            o = re.match(r"\s*-\s*(.+?)\s*(-.*)?$", cs)
            chars = o.group(1)
        if chars == 'Complete':
            chars = ''
        complete = elem['data-statusid'] == '2'
        source = 'favorites' if 'favstories' in elem['class'] else 'authored'
        if source == 'favorites':
            al = elem.find('a', href=re.compile(r"^/u/.*"))
            author = al.string
            o = re.match(r"^/u/(\d+)/.*", al['href'])
            authorid = o.group(1)
            author_url = self.user_url.format(hostname=self.hostname,
                                              number=authorid)
            author_dir = "{}-{}-{}".format(make_filename(author),
                                           self.this_site, authorid)
        else:  # in this case, the caller populates those fields
            author = ''
            authorid = 0
            author_url = ''
            author_dir = ''
        story_url = self.story_url.format(hostname=self.hostname, number=sid,
                                          chapter=1)
        trv = {'title': title, 'category': category, 'id': sid,
               'published': published, 'updated': updated, 'reviews': reviews,
               'chapters': chapters, 'words': words, 'summary': summary,
               'characters': chars, 'complete': complete, 'source': source,
               'author': author, 'authorid': authorid, 'genre': genre,
               'site': self.this_site, 'story_url': story_url,
               'author_url': author_url, 'author_dir': author_dir }
        for i in trv:
            if type(trv[i]) == NavigableString:
                trv[i] = str(trv[i])
        return trv

    def download_list(self, number):
        """Given a user ID, download lists of the stories they've written and favorited
        and return them. The lists are returned as a tuple of (authored,
        faved). Each entry is a dictionary containing metadata.

        """
        url = self.user_url.format(hostname=self.hostname, number=number)
        r = urlopen_retry(url)
        page = r.read().decode()
        soup = BeautifulSoup(page, 'html5lib')
        author = (soup.find('div', id='content_wrapper_inner').span.string.
                  strip())
        auth = []
        fav = []
        author_dir = "{}-{}-{}".format(make_filename(author), self.this_site,
                                       number)
        for i in soup.find_all('div', class_='z-list'):
            a = self._parse_entry(i)
            if a['source'] == 'favorites':
                fav.append(a)
            elif a['source'] == 'authored':
                a['author'] = author
                a['authorid'] = number
                a['author_dir'] = author_dir
                a['author_url'] = url
                auth.append(a)
        info = {'author': author, 'authorid': number, 'site': self.this_site,
                'author_url': url, 'author_dir': author_dir}
        return auth, fav, info

    def get_tags_for(self, md):
        return cat_to_tagset(md['category'])

    def compare_mds(self, r, cr):
        """Check two metadata entries to see if they 1. refer to the same story, 2. at
        the same length. Used to check for updates."""
        try:
            if (r['words'] != cr['words'] or r['chapters'] != cr['chapters'] or
                r['updated'] != cr['updated']):  # noqa: E129
                return False
        except KeyError as e:  # if the metadata is incomplete
            return False
        return True

class FictionPress(FFNet):
    hostname = "www.fictionpress.com"
    this_site = "fictionpress"
