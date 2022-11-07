#!python3

from __future__ import annotations

from typing import (Dict, List, Tuple, Pattern, Any, TextIO, Callable, Set,
                    Optional)
from abc import ABCMeta, abstractmethod
from os.path import join
from .util import make_filename
import attr, datetime, time

@attr.s(auto_attribs=True)
class StoryInfo:
    title: str = attr.ib(converter=str)
    summary: str = attr.ib(converter=str)
    category: str = attr.ib(converter=str)
    id: str = attr.ib(converter=str)
    reviews: int = attr.ib(converter=int)
    chapters: int = attr.ib(converter=int)
    words: int = attr.ib(converter=int)
    characters: str = attr.ib(converter=str)
    source: str = attr.ib(converter=str)
    author: AuthorInfo = attr.ib()
    genre: str = attr.ib(converter=str)
    site: str = attr.ib(converter=str)
    updated: datetime.datetime
    published: datetime.datetime
    complete: bool = attr.ib(converter=bool)
    story_url: str = attr.ib(converter=str)
    tags: Set[str]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StoryInfo:
        authinf = AuthorInfo(
            name=d.pop('author'), id=d.pop('authorid'),
            url=d.pop('author_url'), site=d['site'],
            dir=d.pop('author_dir')
        )

        rv = cls(
            title=d.pop('title'), summary=d.pop('summary'),
            category=d.pop('category'), id=d.pop('id'),
            reviews=d.pop('reviews'), chapters=d.pop('chapters'),
            words=d.pop('words'), characters=d.pop('characters'),
            source=d.pop('source'), author=authinf, genre=d.pop('genre'),
            site=d.pop('site'), updated=d.pop('updated'),
            published=d.pop('published'), complete=d.pop('complete'),
            story_url=d.pop('story_url'), tags=d.pop('tags')
        )

        if len(d) > 0:
            raise ValueError("excess args in dict")

        return rv

    def to_dict(self) -> Dict[str, str]:
        adict = self.author.to_dict()

        rv = { k: str(v) for k, v in self.__dict__.items() }
        rv.pop('author')
        rv.update(adict)

        return rv

    def get_mirror_filename(self) -> str:
        return join(self.author.get_mirror_dirname(),
                    make_filename("{}-{}".format(self.title,
                                                 self.id)))

@attr.s(auto_attribs=True)
class ChapterInfo:
    title: str = attr.ib(converter=str)
    url: str = attr.ib(converter=str)

@attr.s(auto_attribs=True)
class AuthorInfo:
    name: str = attr.ib(converter=str)
    id: str = attr.ib(converter=str)
    url: str = attr.ib(converter=str)
    site: str = attr.ib(converter=str)
    dir: str = attr.ib(converter=str, default='')

    def to_dict(self) -> Dict[str, str]:
        return { 'author': self.name, 'authorid': self.id,
                 'author_url': self.url, 'author_dir': self.dir }

    def get_mirror_dirname(self) -> str:
        return "{}-{}-{}".format(make_filename(self.name),
                                 self.site, self.id)


site_modules: Dict[str, DownloadModule] = {}
url_res: List[Tuple[Pattern, DownloadModule]] = []

class TypeRegister(ABCMeta):
    def __init__(cls, name: str, bases: Tuple[type, ...],
                 datadict: Dict[str, Any]) -> None:
        super().__init__(name, bases, datadict)
        if 'this_site' in datadict and 'url_re' in datadict:
            nc = cls()
            site_modules[datadict['this_site']] = nc
            url_res.append((datadict['url_re'], nc))

class DownloadModule(metaclass=TypeRegister):
    story_url_re: Pattern
    user_url_re: Pattern
    this_site: str

    @abstractmethod
    def get_user_url(self, auth: AuthorInfo) -> str:
        ...

    @abstractmethod
    def get_story_url(self, story: StoryInfo) -> str:
        ...

    @abstractmethod
    def download_metadata(self, sid: str) -> Tuple[StoryInfo,
                                                   List[ChapterInfo]]:
        ...

    # This is a legacy function that downloads an entire story and writes it to
    # a file. The modern mirror format stores chapters separately, so won't use
    # this.
    def compile_story(self, md: StoryInfo, toc: List[ChapterInfo],
                      outfile: TextIO, contents: bool = True,
                      callback: Optional[Callable[[int, str], None]]
                      = None) -> None:
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
""".format(title=md.title, id=md.id, author=md.author.name))
        for k, v in sorted(md.to_dict().items()):
            outfile.write("{}: {}\n".format(k, v))
        outfile.write("-->\n<body>\n")
        outfile.write("<h1>{}</h1>\n".format(md.title))
        if contents:
            outfile.write(self._make_toc(toc))
        for n, t in enumerate(toc):
            time.sleep(2)
            x = n + 1
            if callback:  # For printing progress as it runs.
                callback(n, t.title)
            text = self.download_chapter(t)
            outfile.write("""<h2 id="ch{}" class="chapter">{}</h2>\n""".
                          format(x, t.title))
            outfile.write(text + "\n\n")
        outfile.write("</body>\n</html>\n")

    @abstractmethod
    def download_chapter(self, chapter: ChapterInfo) -> str:
        ...

    @abstractmethod
    def download_list(self, aid: str) -> Tuple[List[StoryInfo],
                                               List[StoryInfo],
                                               AuthorInfo]:
        ...
