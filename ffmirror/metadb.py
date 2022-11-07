# Functions for maintaining a metadata-only mirror in an SQLAlchemy database.
# This may be more feasible to duplicate in its entirety offline.

from __future__ import annotations

from . import site_modules
from .core import StoryInfo, AuthorInfo, ChapterInfo

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (sessionmaker, relationship,  # noqa: F401
                            joinedload, exc)
from sqlalchemy.orm.relationships import RelationshipProperty
from sqlalchemy import create_engine, text, func  # noqa: F401
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy import Table, DateTime, Boolean, Interval
from sqlalchemy.engine.base import Engine

from pathlib import Path

from typing import Union, Tuple, Optional, List, cast, Set, Iterator

import datetime, os, traceback, sys, re

db_file = 'db_test.sqlite'

Base = declarative_base()

fav_stories_table = Table('fav_stories', Base.metadata,
                          Column('author_id', Integer,
                                 ForeignKey('author.id')),
                          Column('story_id', Integer, ForeignKey('story.id')))

fav_authors_table = Table('fav_authors', Base.metadata,
                          Column('author_id', Integer,
                                 ForeignKey('author.id')),
                          Column('favauthor_id', Integer,
                                 ForeignKey('author.id')))

story_tags_table = Table('story_tags', Base.metadata,
                         Column('story_id', Integer, ForeignKey('story.id')),
                         Column('tag_id', Integer, ForeignKey('tag.id')))

following_stories_table = Table('following_stories', Base.metadata,
                                Column('story_id', Integer,
                                       ForeignKey('story.id')))

class Author(Base):
    __tablename__ = 'author'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    archive = Column(String, nullable=False)
    site_id = Column(String, nullable=False)

    md_synced = Column(DateTime)
    sync_int = Column(Interval)

    in_mirror = Column(Boolean, nullable=False, default=False)

    stories_written: RelationshipProperty[List[Story]] = relationship(
        'Story', back_populates='author'
    )
    fav_stories: RelationshipProperty[List[Story]] = relationship(
        'Story', secondary=fav_stories_table,
        backref='users_faved'
    )
    fav_authors: RelationshipProperty[List[Author]] = relationship(
        'Author', secondary=fav_authors_table,
        primaryjoin=id == fav_authors_table.c.author_id,
        secondaryjoin=id == fav_authors_table.c.favauthor_id,
        backref='users_faved'
    )

    def __repr__(self):
        return "<Author name='{}' id='{}'>".format(self.name, self.site_id)

    def get_metadata(self) -> AuthorInfo:
        mod = site_modules[self.archive]
        # md = { 'authorid': self.site_id }
        authinf = AuthorInfo(name=self.name, id=self.site_id,
                             url='', site=self.archive, dir='')
        authinf.dir = authinf.get_mirror_dirname()
        authinf.url = mod.get_user_url(authinf)
        return authinf

    def source_site_url(self):
        return self.get_metadata().url

class Story(Base):
    __tablename__ = 'story'

    id = Column(Integer, primary_key=True)
    title = Column(String)
    archive = Column(String, nullable=False)
    site_id = Column(String, nullable=False)
    words = Column(Integer)
    chapters = Column(Integer)
    published = Column(DateTime)
    updated = Column(DateTime)
    category = Column(String)
    summary = Column(String)
    characters = Column(String)
    complete = Column(Boolean)
    genre = Column(String)

    download_time = Column(DateTime)  # null if never downloaded
    download_fn = Column(String)

    author_id = Column(Integer, ForeignKey('author.id'))

    author = relationship('Author', back_populates='stories_written')

    tags = relationship('Tag', secondary=story_tags_table,
                        backref='stories', uselist=True)

    all_chapters = relationship('Chapter', back_populates='story',
                                order_by='Chapter.num')

    def get_metadata(self) -> StoryInfo:
        site = self.archive
        mod = site_modules[site]
        authinf = self.author.get_metadata()
        chapters = self.chapters or -1
        words = self.words or -1
        assert self.updated is not None
        assert self.published is not None
        ts = cast(Set[str], set(i.name for i in self.tags if i))
        rv = StoryInfo(
            title=self.title, summary=self.summary, category=self.category,
            id=self.site_id, reviews=-1, chapters=chapters, words=words,
            characters=self.characters, source='', author=authinf,
            genre=self.genre, site=self.archive, updated=self.updated,
            published=self.published, complete=self.complete, story_url='',
            tags=ts
        )
        rv.story_url = mod.get_story_url(rv)
        return rv

    def unique_filename(self) -> str:
        tmd = self.get_metadata()
        # return story_file(tmd, with_id=True)
        return tmd.get_mirror_filename()

    def __repr__(self) -> str:
        return "<Story '{}' by '{}' id='{}'>".format(
            self.title, self.author.name, self.site_id)

class Chapter(Base):
    __tablename__ = 'chapter'

    id = Column(Integer, primary_key=True)
    title = Column(String)
    num = Column(Integer)
    story_id = Column(Integer, ForeignKey('story.id'))

    story = relationship('Story', back_populates='all_chapters')

class Tag(Base):
    __tablename__ = 'tag'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    date_added = Column(DateTime, default=datetime.datetime.now)

    def __repr__(self) -> str:
        return "<Tag '{}'>".format(self.name)

class Config(Base):
    __tablename__ = 'config'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    value = Column(String)

    def __repr__(self) -> str:
        return "<Config '{}'='{}'>".format(self.name, self.value)

class DBMirror(object):
    def __init__(self, mdir: str, debug: bool = False) -> None:
        self.engine: Optional[Engine] = None
        self.Session: Optional[sessionmaker] = None
        self.mdir = os.path.abspath(mdir)
        self.db_file = os.path.join(self.mdir, 'ffmeta.sqlite')
        self.debug = debug
        self._last_ao = None

    def __enter__(self) -> DBMirror:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # any method which changes the DB will call ds.commit() on its own
        self.ds.close()

    def connect(self) -> None:
        self.engine = create_engine('sqlite:///{}'.format(self.db_file),
                                    echo=self.debug)
        self.Session = sessionmaker(bind=self.engine)
        self.ds = self.Session()

    def create(self) -> None:
        Base.metadata.create_all(self.engine)
        co = Config(name='archive_dir', value=self.mdir)
        self.ds.add(co)
        self.ds.commit()

    def get_story(self, archive: str, sid: str) -> Story:
        so_rv = (self.ds.query(Story)
                 .filter((Story.archive == archive) & (Story.site_id == sid)).
                 one_or_none())
        return so_rv

    def get_author(self, archive: str, aid: str) -> Author:
        return (self.ds.query(Author)
                .filter_by(archive=archive).filter_by(site_id=aid).
                one_or_none())

    def cache_load_author(self, ao: Author) -> Author:
        return (self.ds.query(Author)
                .options(joinedload(Author.stories_written),
                         joinedload(Author.fav_stories).joinedload('author'))
                .filter_by(id=ao.id).one_or_none())

    def get_config(self, name: str) -> str:
        return self.ds.query(Config).filter_by(name=name).first().value

    def _handle_tags_for(self, md: StoryInfo) -> None:
        """Takes a story metadata object, fetches its tags via its respective site
        module, then adds them to that story in the database. Tags that do not
        exist will be created. Requires that the story object already exist.
        This method does not call ds.commit(); a caller MUST do so.

        """
        ds = self.ds
        so = self.get_story(md.site, md.id)
        for t in md.tags:
            to = ds.query(Tag).filter_by(name=t).first()
            if not to:
                to = Tag(name=t)
                ds.add(to)
            if so not in to.stories:
                to.stories.append(so)

    def _check_update(self, so: Story, s: StoryInfo) -> bool:
        return (so.words != s.words or so.chapters != s.chapters or
                so.updated != s.updated)

    def _story_from_md(self, s: StoryInfo, ao: Author,
                       eso: Story = None):
        """Gets or creates a Story object from an ffmirror metadata dictionary. If it
        did not already exist, the object is added to the database session. If
        it did, it is updated to match the parameters. This method does not
        call ds.commit(); a caller MUST do so.

        """
        ds = self.ds
        if eso:
            so = eso
        else:
            so = self.get_story(s.site, s.id)
        if not so:
            so = Story(archive=s.site, site_id=s.id)
            ds.add(so)
        if self._check_update(so, s):
            so.title = s.title
            so.words = s.words
            so.chapters = s.chapters
            so.category = s.category
            so.summary = s.summary
            so.characters = s.characters
            so.complete = s.complete
            so.genre = s.genre
            so.published = s.published
            so.updated = s.updated
            self._handle_tags_for(s)
            so.author = ao
        return so

    def sync_author(self, ido: Union[Author, Tuple[str, str]]) -> None:
        ds = self.ds
        if isinstance(ido, Author):
            ao = ido
            archive, aid = ao.archive, ao.site_id
        else:
            archive, aid = ido
            ao = self.get_author(archive, aid)
        mod = site_modules[archive]
        auth, fav, info = mod.download_list(aid)
        if not ao:
            ao = Author(name=info.name, archive=archive, site_id=aid)
            ao.sync_int = datetime.timedelta(days=1)
            ds.add(ao)
        else:
            ao = self.cache_load_author(ao)
        ao.md_synced = datetime.datetime.now()
        si_d = {}
        for s in ao.stories_written + ao.fav_stories:
            si_d[s.site_id] = s
        for sm in auth:
            so = self._story_from_md(sm, ao, si_d.get(sm.id))
        for sm in fav:
            ms = si_d.get(sm.id)
            fao = ms.author if ms else self.get_author(archive, sm.author.id)
            if not fao:
                fao = Author(name=sm.author.name, archive=archive,
                             site_id=sm.author.id)
                ds.add(fao)
            so = self._story_from_md(sm, fao, ms)
            if so not in ao.fav_stories:
                ao.fav_stories.append(so)
        ds.commit()

    def _set_chapters(self, s: Story, toc: List[ChapterInfo]) -> None:
        n_chapters = len(s.all_chapters)
        for n, i in enumerate(toc):
            if n < n_chapters:
                s.all_chapters[n].title = i.title
            else:
                c = Chapter(title=i.title, num=n)
                s.all_chapters.append(c)

    def story_to_archive(self, st: Story, silent: bool = False,
                         commit: bool = True) -> None:
        if not silent:
            print("Downloading story '{}'".format(st.title))
        mod = site_modules[st.archive]
        md, toc = mod.download_metadata(st.site_id)
        # if rfn is None:
        rfn = md.get_mirror_filename()
        st_dir = Path(os.path.join(self.mdir, rfn))
        st_dir.mkdir(exist_ok=True, parents=True)

        for n, c in enumerate(toc):
            if not silent:
                print(f"\r\x1b[2Kch.{n + 1}/{st.chapters}: {c.title}", end='')
            chap_data = mod.download_chapter(c)
            fn = f"{n:04d}.html"
            (st_dir / fn).write_text(chap_data)
        if not silent:
            print('', end='\n')
        st.download_fn = rfn
        st.download_time = datetime.datetime.now()
        if commit:
            self.ds.commit()

    def archive_author(self, ao: Author, silent: bool = False) -> None:
        ds = self.ds
        ao.in_mirror = True
        try:
            for i in ds.query(Story).filter((Story.author == ao) &
                                            ((Story.download_time == None) |  # noqa: E711,E501
                                             (Story.download_time <
                                              Story.updated))).all():
                try:
                    self.story_to_archive(i, silent=silent, commit=False)
                except Exception:
                    if not silent:
                        print("Download failed")
                        traceback.print_exc(file=sys.stdout)
        finally:
            ds.commit()

    def run_update(self, silent: bool = False,
                   max_authors: Optional[int] = None) -> None:
        ds = self.ds
        aq = (ds.query(Author).filter(Author.in_mirror == True).  # noqa: E712
              order_by(Author.md_synced.asc()))
        ta = aq.count()
        for n, i in enumerate(aq.all()):
            if max_authors is not None and n >= max_authors:
                break
            if not silent:
                print("Syncing author {} ({}/{})".format(i.name, n + 1, ta))
            self.sync_author(i)
            self.archive_author(i, silent=silent)

def extract_chapters(stp: Path) -> Iterator[Tuple[str, str]]:
    with stp.open('r') as stf:
        cur_chap = None
        cur_name = None
        for l in stf:
            if l.startswith('<h2 id="ch'):
                if cur_chap is not None:
                    yield (cur_name, cur_chap)
                o = re.match(r"<h2[^>]*>([^<]*)</h2>", l)
                cur_name = o.group(1)
                cur_chap = ''
            elif l.startswith('</body>'):
                yield (cur_name, cur_chap)
                return
            else:
                if cur_chap is not None:
                    cur_chap += l

# Migrate a mirror from the single-file compile_story form to the chapters
# form.
def update_chapters(db_path: Path) -> None:
    m = DBMirror(str(db_path))
    with m:
        tot = m.ds.query(Story).count()
        for sn, s in enumerate(m.ds.query(Story).all()):
            if not s.download_fn:
                continue
            fp = db_path / s.download_fn
            if not fp.is_file():
                continue
            print(f"\r\x1b[2KStory {sn + 1}/{tot}: {s.title}", end='')
            dbn = s.download_fn.rsplit('.', maxsplit=1)[0]
            dp = db_path / dbn
            dp.mkdir(exist_ok=True, parents=True)
            for n, t in enumerate(extract_chapters(fp)):
                fn = f"{n:04d}.html"
                (dp / fn).write_text(t[1])
                c = Chapter(title=t[0], num=n)
                s.all_chapters.append(c)
            s.download_fn = dbn
            m.ds.commit()

# Temp functions for mirror migrate.

def get_archive_id(dn: str) -> Tuple[str, str]:
    rv = dn.rsplit('-', 2)
    return rv[-2], rv[-1]

def populate_from_db(db, mm):
    import itertools
    all_stories = list(itertools.chain.from_iterable([i.stories for i in
                                                      db.values()]))
    for s in all_stories:
        so = mm.get_story(s['site'], s['id'])
        if not so:
            ao = mm.get_author(s['site'], s['authorid'])
            if not ao:
                raise ValueError("author not in db for story: {}".format(s))
            if 'complete' not in s:
                s['complete'] = False
            if type(s['complete']) != bool:
                s['complete'] = s['complete'] == 'True'
            if 'genre' not in s:
                s['genre'] = None
            so = mm._story_from_md(s, ao)
            print("Adding story not in db: {}".format(s))
        rfn = os.path.join(mm.mdir, s['filename'])
        if not os.path.exists(rfn):
            raise ValueError("file doesn't exist: {}".format(rfn))
        mt = datetime.datetime.fromtimestamp(os.stat(rfn).st_mtime)
        so.download_time = mt
        so.download_fn = s['filename']
    mm.ds.commit()
