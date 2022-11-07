# This is the site module for FF.net, and the model for other site modules. It
# handles only FF.net-specific tasks; the API provided includes
# download_metadata, compile_story, and download_list. The functions can be
# called on their own, but it's probably friendlier to use the runner in
# __main__ or the update functions in mirror. Also handles FictionPress, since
# they're identical.

import re, time
from bs4 import BeautifulSoup  # type: ignore
from bs4.element import Tag  # type: ignore
from datetime import datetime

from typing import Set, List, Tuple, Optional, Callable, TextIO

from ..util import (make_filename, urlopen_retry,
                    fold_string_indiscriminately)
from ..core import DownloadModule, StoryInfo, AuthorInfo, ChapterInfo

def cat_to_tagset(category: str) -> Set[str]:
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
class FFNet(DownloadModule):
    hostname = "www.fanfiction.net"
    this_site = "ffnet"
    story_url = "https://{hostname}/s/{number}/{chapter}/"
    user_url = "https://{hostname}/u/{number}/"

    file_version = 3  # for metadata check

    url_re = re.compile(r"^https://" + hostname + "/")
    story_url_re = re.compile(r"https?://(?P<hostname>[^/]+)/s/(?P<sid>\d+)/?(?P<chl>\d+)?/?")  # noqa: E501
    user_url_re = re.compile(r"https?://(?P<hostname>[^/]+)/u/(?P<aid>\d+)/?")

    def get_user_url(self, md: AuthorInfo) -> str:
        return self.user_url.format(number=md.id,
                                    hostname=self.hostname)

    def get_story_url(self, md: StoryInfo) -> str:
        return self.story_url.format(number=md.id, chapter=1,
                                     hostname=self.hostname)

    # Functions related to downloading stories

    def _get_contents(self, soup: BeautifulSoup,
                      sid: str) -> List[ChapterInfo]:
        """Given a BeautifulSoup of a story page, extract the contents list and
        return list of chapter titles."""
        se = soup.find("select", id="chap_select")
        if se is None:
            # it's a oneshot, so no chapter list
            return [
                ChapterInfo(title='Chapter 1',
                            url=self.story_url.format(
                                hostname=self.hostname, number=sid, chapter=1
                            ))]
        rv: List[ChapterInfo] = []
        for n, oe in enumerate(se.find_all('option')):
            o = re.match(r"\d+. (.*)", oe.string)
            assert o is not None
            val = o.group(1)
            rv.append(
                ChapterInfo(title=val,
                            url=self.story_url.format(
                                hostname=self.hostname, number=sid, chapter=n
                            )))
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

    def _get_storytext(self, d: str) -> str:
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

    def _get_metadata(self, soup: BeautifulSoup) -> StoryInfo:
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
        o = re.match(r"/u/(\d+)/.*", ae['href'])
        assert o is not None
        authorid = o.group(1)
        sd = e.find("div", class_='xcontrast_txt')
        summary = sd.string
        md = sd.find_next_sibling("span", class_='xcontrast_txt')
        s = md.a.next_sibling
        o = re.match(r"[ -]+\w+[ -]+((?P<genre>[\w/]+) - )?((?P<chars>(?!Chapters).*?\S) +- +)?(Chapters: (?P<chaps>\d+)[ -]+)?Words: (?P<words>[\d,]+).*", s)  # noqa: E501
        assert o is not None
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
        o = re.match(r".*id: (\d+).*", ids)
        assert o is not None
        sid = o.group(1)
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
        authinf = AuthorInfo(name=author, id=authorid, url=author_url,
                             site=self.this_site, dir=author_dir)
        storyinf = StoryInfo(
            title=title, summary=summary, category=category, id=sid,
            reviews=reviews, chapters=chapters, words=words,
            characters=characters, source='story', author=authinf, genre=genre,
            site=self.this_site, updated=datetime.fromtimestamp(updated),
            published=datetime.fromtimestamp(published),
            complete=complete, story_url=story_url,
            tags=cat_to_tagset(category)
        )
        return storyinf

    def _make_toc(self, contents: List[ChapterInfo]) -> str:
        """Makes an HTML string table of contents to be concatenated into outstr, given
        the return value of _get_contents (array of chapter names).

        """
        rs = "<h2>Contents</h2>\n<ol>\n"
        for x in range(len(contents)):
            n = x + 1
            anc = "#ch{}".format(n)
            rs += "<li><a href=\"{}\">{}</a></li>\n".format(anc,
                                                            contents[x].title)
        rs += "</ol>\n"
        return rs

    def download_metadata(self, number: str) -> Tuple[StoryInfo,
                                                      List[ChapterInfo]]:
        """This function takes a fic number and returns a pair: the first is a
        dictionary of the story's metadata, the second is sufficient
        information to download all its individual chapters.

        """
        url = self.story_url.format(hostname=self.hostname, number=number,
                                    chapter=1)
        r = urlopen_retry(url, use_cloudscraper=True)
        assert r is not None
        data = r.read()
        soup = BeautifulSoup(data, 'html5lib')
        md = self._get_metadata(soup)
        toc = self._get_contents(soup, number)
        return md, toc

    def download_chapter(self, chapter: ChapterInfo) -> str:
        r = urlopen_retry(chapter.url, use_cloudscraper=True)
        assert r is not None
        data = r.read().decode()
        text = self._get_storytext(data)
        text = fold_string_indiscriminately(text)
        return text

    # Functions related to dealing with user listings

    def _parse_entry(self, elem: Tag) -> StoryInfo:
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
        assert o is not None
        genre = o.group('genre')
        if 'Chapters' in genre:
            genre = ''
        cs = sd.contents[-1]
        if type(cs) == Tag:
            chars = ''
        else:
            o = re.match(r"\s*-\s+(.+?)(\s+-.*)?$", cs)
            assert o is not None
            chars = o.group(1)
        if chars == 'Complete':
            chars = ''
        complete = elem['data-statusid'] == '2'
        source = 'favorites' if 'favstories' in elem['class'] else 'authored'
        if source == 'favorites':
            al = elem.find('a', href=re.compile(r"^/u/.*"))
            author = al.string
            o = re.match(r"^/u/(\d+)/.*", al['href'])
            assert o is not None
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
        authinfo = AuthorInfo(name=author, id=authorid, url=author_url,
                              site=self.this_site, dir=author_dir)
        storyinfo = StoryInfo(
            title=title, category=category, id=sid,
            published=datetime.fromtimestamp(published),
            updated=datetime.fromtimestamp(updated),
            reviews=reviews, chapters=chapters, words=words, summary=summary,
            characters=chars, complete=complete, source=source,
            author=authinfo, genre=genre, site=self.this_site,
            story_url=story_url, tags=cat_to_tagset(category)
        )
        return storyinfo

    def download_list(self, number: str) -> Tuple[List[StoryInfo],
                                                  List[StoryInfo],
                                                  AuthorInfo]:
        """Given a user ID, download lists of the stories they've written and favorited
        and return them. The lists are returned as a tuple of (authored,
        faved). Each entry is a dictionary containing metadata.

        """
        try:
            url = self.user_url.format(hostname=self.hostname, number=number)
            r = urlopen_retry(url, use_cloudscraper=True)
            assert r is not None
            page = r.read().decode()
            soup = BeautifulSoup(page, 'html5lib')
            author = (soup.find('div', id='content_wrapper_inner').span.string.
                      strip())
            auth: List[StoryInfo] = []
            fav: List[StoryInfo] = []
            author_dir = "{}-{}-{}".format(make_filename(author),
                                           self.this_site,
                                           number)
            for i in soup.find_all('div', class_='z-list'):
                a = self._parse_entry(i)
                if a.source == 'favorites':
                    fav.append(a)
                elif a.source == 'authored':
                    a.author.name = author
                    a.author.id = number
                    a.author.dir = author_dir
                    a.author.url = url
                    auth.append(a)
            info = AuthorInfo(name=author, id=number, site=self.this_site,
                              url=url, dir=author_dir)
        except Exception:
            print(url)
            raise
        return auth, fav, info

    def compare_mds(self, r: StoryInfo, cr: StoryInfo) -> bool:
        """Check two metadata entries to see if they 1. refer to the same story, 2. at
        the same length. Used to check for updates."""
        if (r.words != cr.words or r.chapters != cr.chapters or
            r.updated != cr.updated):  # noqa: E129
            return False
        return True

class FictionPress(FFNet):
    hostname = "www.fictionpress.com"
    this_site = "fictionpress"
    url_re = re.compile(r"^https://" + hostname + "/")
