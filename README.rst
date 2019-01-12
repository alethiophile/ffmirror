This package is designed to deal with downloading stories from FF.net and,
later, other sites. Dependencies:

 - Python 3 (tested under 3.3.2)
 - BeautifulSoup version 4
 - html5lib

html5lib is never directly referenced by ffmirror, but BeautifulSoup will use it
as the parser if it is present; the default parser is unable to handle the
incorrect HTML emitted by fanfiction.net.

To install, place the ffmirror directory somewhere that's included in
PYTHONPATH. After that, you can run it by any of the following means:

 - Run 'python3 -m ffmirror <modulename>'
 - Run the __main__.py file directly, giving <modulename> as first argument
 - Create symlinks to __main__.py somewhere in PATH, named after the modules;
   run the correct symlink for each module

The modules currently extant are the following:

 - ffdl
 - ffadd
 - ffup
 - ffcache

ffdl is a simple one-story downloader. ffadd, ffup and ffcache all deal with an
offline mirror; the location of that mirror is taken to be the current working
directory where the files are run. ffadd will add an author's corpus or
favorites to the current mirror. ffup will update an entire mirror by checking
all authors in it. ffcache will create an index cache file (index.db) required
for using CGI scripts to browse the mirror. The options are all documented by
the usual --help invocation of each command.

In addition to its local mirroring functionality, ffmirror can be used alongside
calibre's ebook-convert to easily maintain a library of fanfiction on a Kindle
or other ebook reader. The file Makefile.sample in this directory provides an
example for use with Kindle.