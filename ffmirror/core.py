#!python3

from __future__ import annotations

from typing import Dict, List, Tuple, Pattern, Any, TextIO, Callable, Set
from abc import ABCMeta, abstractmethod
import attr, datetime

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

    @abstractmethod
    def compile_story(self, story: StoryInfo, toc: List[ChapterInfo],
                      outfile: TextIO,
                      callback: Callable[[int, str], None]) -> None:
        ...

    @abstractmethod
    def download_list(self, aid: str) -> Tuple[List[StoryInfo],
                                               List[StoryInfo],
                                               AuthorInfo]:
        ...

    @abstractmethod
    def get_tags_for(self, story: StoryInfo) -> Set[str]:
        ...
