ffmirror is a program to create and maintain a local mirror of stories on
fiction-publishing sites. It has functionality for downloading stories similar
to FanFicFare or other projects, but the differentiating factor is support for
creating a local database that maintains downloaded metadata and can
automatically update authors that are followed.

ffmirror has two currently maintained script entry points:

 - ffdl is a simple one-story file downloader. It takes a single URL and writes
   an HTML file story.
 - ffdb is the manager for local fanfic site mirrors. These maintain a local
   copy of metadata for a set of followed users alongside copies of all their
   stories.

The remaining entry points, ffadd, ffup, ffcache are designed for an older
format of mirror, and are now deprecated.

ffmirror can be installed via PyPI: ``pip install ffmirror``

To create a mirror, enter an empty directory and issue:

.. code:: bash

  $ ffdb init

This initializes the SQLite database that tracks metadata. You can now add
authors by issuing:

.. code:: bash

  $ ffdb add $AUTHOR_URL

Adding an author will immediately download all their stories into the mirror.
Stories are stored under top-level directories per author.

Updating the mirror will recheck all authors that have been added and download
any new or updated stories. To update the mirror, issue:

.. code:: bash

  $ ffdb update

You can update only one author by issuing:

.. code:: bash

  $ ffdb update $AUTHOR_DIR

where AUTHOR_DIR is the directory with that author's stories.
