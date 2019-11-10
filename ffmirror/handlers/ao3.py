# Site module for Archive Of Our Own.

import re
from bs4 import BeautifulSoup  # type: ignore
from bs4.element import Tag  # type: ignore
# from urllib.parse import urljoin
from datetime import datetime
import html2text  # type: ignore

from typing import Dict, Any, Tuple, List, Set, Optional

from ..util import urlopen_retry, rectify_strings, make_filename

def parse_int(s):
    return int(s.replace(',', ''))

class AO3(object):
    hostname = "archiveofourown.org"
    this_site = "ao3"
    story_url = "https://{hostname}/works/{number}"
    user_url = "https://{hostname}/users/{aid}/works"
    user_bookmarks_url = "https://{hostname}/users/{aid}/bookmarks"

    def get_user_url(self, md: Dict[str, Any]) -> str:
        return self.user_url.format(aid=md['authorid'], hostname=self.hostname)

    def get_story_url(self, md: Dict[str, Any]) -> str:
        return self.story_url.format(number=md['id'], hostname=self.hostname)

    def _parse_html_entry(self, i: Tag) -> Optional[Dict[str, Any]]:
        rv = {}
        o = i.p
        if o is not None and 'message' in o['class']:
            return None
        hh = i.find('h4', class_='heading')
        rv['title'] = hh.a.string
        if 'series' in hh.a['href']:
            return None
        o = re.search(r'\d+', hh.a['href'])
        assert o is not None
        rv['id'] = o.group(0)
        al = hh.find('a', rel='author')
        rv['author'] = al.string
        o = re.match(r'/users/(\w+)/', al['href'])
        assert o is not None
        rv['authorid'] = o.group(1)
        fandoms = [l.string for l in i.find('h5', class_='fandoms')
                   ('a', class_='tag')]
        rv['category'] = ' & '.join(fandoms)
        rv['updated'] = int(datetime.
                            strptime(i.find('div', class_='header').
                                     find('p', class_='datetime').string,
                                     "%d %b %Y").timestamp())
        rv['tags'] = set(fandoms)

        rt = i.find('ul', class_='required-tags')
        rating = rt.find('span', class_='rating').get_text().strip().lower()
        rv['tags'].add(f"rating: {rating}")
        rels = rt.find('span', class_='category')['title'].split(', ')
        rv['tags'].update([f"relationships: {l}" for l in rels])
        rv['complete'] = ('complete-yes' in rt.find('span', class_='iswip')
                          ['class'])

        tl = i.find('ul', class_='tags')
        for t in tl('li'):
            ts = t.find('a', class_='tag').string
            rv['tags'].add(ts)

        ht = html2text.HTML2Text()
        ht.ignore_links = True
        ht.ignore_tables = True
        ht.body_width = 0
        se = i.find('blockquote', class_='summary')
        se.name = 'div'
        rv['summary'] = ht.handle(str(se))
        se = i.find('dl', class_='stats')
        rv['language'] = se.find('dd', class_='language').string
        rv['words'] = parse_int(se.find('dd', class_='words').string)
        rv['chapters'] = parse_int(se.find('dd', class_='chapters').string.
                                   split('/')[0])
        try:
            rv['reviews'] = parse_int(se.find('dd', class_='comments').
                                      get_text().strip())
        except Exception:
            rv['reviews'] = 0
        return rectify_strings(rv)

    def download_list(self, number: str) -> Tuple[List[Dict[str, Any]],
                                                  List[Dict[str, Any]],
                                                  Dict[str, Any]]:
        """Despite the name, "number" is just the string username from the URL."""
        url = self.user_url.format(hostname=self.hostname, aid=number)
        data = urlopen_retry(url)
        assert data is not None
        soup = BeautifulSoup(data.read(), 'html5lib')

        def download_with_pages(url):
            rv = []
            page = urlopen_retry(url).read()
            soup = BeautifulSoup(page, 'html5lib')

            def make_page(n):
                return url + '?page=' + str(n)

            def get_page(u):
                if 'page=' not in u:
                    return 1
                else:
                    return int(re.search(r'page=(\d+)', u).group(1))

            pl = soup.find('ol', class_='pagination')
            if pl:
                max_page = max(get_page(i['href']) for i in pl('a'))
            else:
                max_page = 1

            def parse_page(soup):
                e = soup.find('div', id='main').find('ol', class_='index')
                for i in e('li', class_='blurb'):
                    try:
                        r = self._parse_html_entry(i)
                        if r is not None:
                            rv.append(r)
                    except Exception:
                        print(i)
                        raise

            parse_page(soup)
            for i in range(2, max_page + 1):
                u = make_page(i)
                s = BeautifulSoup(urlopen_retry(u).read(), 'html5lib')
                parse_page(s)

            return rv

        auth = download_with_pages(url)
        fav_url = self.user_bookmarks_url.format(hostname=self.hostname,
                                                 aid=number)
        fav = download_with_pages(fav_url)

        aname = (soup.find('div', id='main').find('h2', class_='heading').
                 string.split(' Works by ')[1].strip())
        author_dir = "{}-{}-{}".format(make_filename(aname), self.this_site,
                                       number)
        info = { 'author': aname, 'authorid': number, 'site': self.this_site,
                 'author_url': url, 'author_dir': author_dir }
        return auth, fav, info

    def get_tags_for(self, md: Dict[str, Any]) -> Set[str]:
        return md['tags']

    def download_metadata(self, number):
        url = self.story_url.format(hostname=self.hostname, number=number)
