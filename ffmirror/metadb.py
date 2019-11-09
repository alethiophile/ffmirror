# Functions for maintaining a metadata-only mirror in an SQLAlchemy database.
# This may be more feasible to duplicate in its entirety offline.

from ffmirror import sites
from ffmirror.mirror import story_file

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (sessionmaker, relationship,  # noqa: F401
                            joinedload, exc)
from sqlalchemy import create_engine, text, func  # noqa: F401
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy import Table, DateTime, Boolean, Interval

import datetime, os, traceback, sys

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

class Author(Base):
    __tablename__ = 'author'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    archive = Column(String, nullable=False)
    site_id = Column(String, nullable=False)

    md_synced = Column(DateTime)
    sync_int = Column(Interval)

    in_mirror = Column(Boolean, nullable=False, default=False)

    stories_written = relationship('Story', backref='author')
    fav_stories = relationship('Story', secondary=fav_stories_table,
                               backref='users_faved')
    fav_authors = relationship('Author', secondary=fav_authors_table,
                               primaryjoin=id == fav_authors_table.c.author_id,
                               secondaryjoin=id ==
                               fav_authors_table.c.favauthor_id,
                               backref='users_faved')

    def __repr__(self):
        return "<Author name='{}' id='{}'>".format(self.name, self.site_id)

    def source_site_url(self):
        mod = sites[self.archive]
        md = { 'authorid': self.site_id }
        return mod.get_user_url(md)

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

    tags = relationship('Tag', secondary=story_tags_table,
                        backref='stories')

    def get_metadata(self):
        return {'author': self.author.name, 'site': self.archive,
                'authorid': self.author.site_id, 'title': self.title,
                'id': self.site_id}

    def unique_filename(self):
        tmd = self.get_metadata()
        return story_file(tmd, with_id=True)

    def __repr__(self):
        return "<Story '{}' by '{}' id='{}'>".format(
            self.title, self.author.name, self.site_id)

class Tag(Base):
    __tablename__ = 'tag'

    id = Column(Integer, primary_key=True)
    name = Column(String)

    def __repr__(self):
        return "<Tag '{}'>".format(self.name)

class Config(Base):
    __tablename__ = 'config'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    value = Column(String)

    def __repr__(self):
        return "<Config '{}'='{}'>".format(self.name, self.value)

class DBMirror(object):
    def __init__(self, mdir, debug=False):
        self.engine = None
        self.Session = None
        self.mdir = os.path.abspath(mdir)
        self.db_file = os.path.join(self.mdir, 'ffmeta.sqlite')
        self.debug = debug
        self._last_ao = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # any method which changes the DB will call ds.commit() on its own
        self.ds.close()

    def connect(self):
        self.engine = create_engine('sqlite:///{}'.format(self.db_file),
                                    echo=self.debug)
        self.Session = sessionmaker(bind=self.engine)
        self.ds = self.Session()

    def create(self):
        Base.metadata.create_all(self.engine)
        co = Config(name='archive_dir', value=self.mdir)
        self.ds.add(co)
        self.ds.commit()

    def get_story(self, archive, sid):
        so_rv = (self.ds.query(Story)
                 .filter((Story.archive == archive) & (Story.site_id == sid)).
                 one_or_none())
        return so_rv

    def get_author(self, archive, aid):
        return (self.ds.query(Author)
                .filter_by(archive=archive).filter_by(site_id=aid).
                one_or_none())

    def cache_load_author(self, ao):
        return (self.ds.query(Author)
                .options(joinedload(Author.stories_written),
                         joinedload(Author.fav_stories).joinedload('author'))
                .filter_by(id=ao.id).one_or_none())

    def get_config(self, name):
        return self.ds.query(Config).filter_by(name=name).first().value

    def _handle_tags_for(self, md):
        """Takes a story metadata object, fetches its tags via its respective site
        module, then adds them to that story in the database. Tags that do not
        exist will be created. Requires that the story object already exist.
        This method does not call ds.commit(); a caller MUST do so.

        """
        ds = self.ds
        tagset = sites[md['site']].get_tags_for(md)
        so = self.get_story(md['site'], md['id'])
        for t in tagset:
            to = ds.query(Tag).filter_by(name=t).first()
            if not to:
                to = Tag(name=t)
                ds.add(to)
            if so not in to.stories:
                to.stories.append(so)

    def _check_update(self, so, s):
        return (so.words != s['words'] or so.chapters != s['chapters'] or
                so.updated != datetime.datetime.fromtimestamp(s['updated']))

    def _story_from_md(self, s, ao, eso=None):
        """Gets or creates a Story object from an ffmirror metadata dictionary. If it
        did not already exist, the object is added to the database session. If
        it did, it is updated to match the parameters. This method does not
        call ds.commit(); a caller MUST do so.

        """
        ds = self.ds
        if eso:
            so = eso
        else:
            so = self.get_story(s['site'], s['id'])
        if not so:
            so = Story(archive=s['site'], site_id=s['id'])
            ds.add(so)
        if self._check_update(so, s):
            for di in ['title', 'words', 'chapters', 'category', 'summary',
                       'characters', 'complete', 'genre']:
                setattr(so, di, s[di])
            for di in ['published', 'updated']:
                setattr(so, di, datetime.datetime.fromtimestamp(s[di]))
            self._handle_tags_for(s)
            so.author = ao
        return so

    def sync_author(self, ido):
        ds = self.ds
        if isinstance(ido, Author):
            ao = ido
            archive, aid = ao.archive, ao.site_id
        else:
            archive, aid = ido
            ao = self.get_author(archive, aid)
        mod = sites[archive]
        auth, fav, info = mod.download_list(aid)
        if not ao:
            ao = Author(name=info['author'], archive=archive, site_id=aid)
            ao.sync_int = datetime.timedelta(days=1)
            ds.add(ao)
        else:
            ao = self.cache_load_author(ao)
        ao.md_synced = datetime.datetime.now()
        si_d = {}
        for s in ao.stories_written + ao.fav_stories:
            si_d[s.site_id] = s
        for s in auth:
            so = self._story_from_md(s, ao, si_d.get(s['id']))
        for s in fav:
            ms = si_d.get(s['id'])
            fao = ms.author if ms else self.get_author(archive, s['authorid'])
            if not fao:
                fao = Author(name=s['author'], archive=archive,
                             site_id=s['authorid'])
                ds.add(fao)
            so = self._story_from_md(s, fao, ms)
            if so not in ao.fav_stories:
                ao.fav_stories.append(so)
        ds.commit()

    def story_to_archive(self, i, rfn=None, silent=False):
        if not silent:
            print("Downloading story '{}'".format(i.title))
        mod = sites[i.archive]
        md, toc = mod.download_metadata(i.site_id)
        if rfn is None:
            rfn = story_file(md, with_id=True)
        fn = os.path.join(self.mdir, rfn)
        os.makedirs(os.path.split(fn)[0], exist_ok=True)

        def ocf(n, t):
            if not silent:
                print("\r\x1b[2Kch.{}/{}: {}".format(n + 1,
                                                     i.chapters, t), end='')
        with open(fn, 'w') as out:
            mod.compile_story(md, toc, out, contents=True, callback=ocf)
        if not silent:
            print('', end='\n')
        i.download_fn = rfn
        i.download_time = datetime.datetime.now()

    def archive_author(self, ao, silent=False):
        ds = self.ds
        ao.in_mirror = True
        try:
            for i in ds.query(Story).filter((Story.author == ao) &
                                            ((Story.download_time == None) |  # noqa: E711,E501
                                             (Story.download_time <
                                              Story.updated))).all():
                try:
                    self.story_to_archive(i, silent=silent)
                except Exception as e:
                    if not silent:
                        print("Download failed")
                        traceback.print_exc(file=sys.stdout)
        finally:
            ds.commit()

    def run_update(self, silent=False):
        ds = self.ds
        aq = (ds.query(Author).filter(Author.in_mirror == True).  # noqa: E712
              order_by(Author.md_synced.asc()))
        ta = aq.count()
        for n, i in enumerate(aq.all()):
            if not silent:
                print("Syncing author {} ({}/{})".format(i.name, n + 1, ta))
            self.sync_author(i)
            self.archive_author(i, silent=silent)

# Temp functions for mirror migrate.

def get_archive_id(dn):
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
