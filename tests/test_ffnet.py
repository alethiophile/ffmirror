#!/usr/bin/python

import ffmirror.ffnet, datetime
import unittest, unittest.mock

# This is a base class for test cases, but not a functional test case itself,
# so it doesn't inherit from TestCase.
class TestGetterModule(object):
    def setUp(self):
        self.getter = self.getter_class()

    def test_getlist(self):
        o = self.getter.user_url_re.match(self.user_test_url)
        self.assertTrue(o is not None)
        aid = o.group('number')
        self._check_valid_aid(aid)
        
        auth, faved = self.getter.download_list(aid)
        self.assertTrue(len(auth) > 0)
        self.assertTrue(len(faved) > 0)
        for i in auth + faved:
            self._check_valid_metadata(i)

        ca, ci = auth[0]['author'], auth[0]['authorid']
        for i in auth:
            self.assertEqual(i['author'], ca)
            self.assertEqual(i['authorid'], ci)

    def _check_valid_metadata(self, md):
        for i in self.field_list:
            self.assertTrue(i in md)

        for i in self.field_ints:
            self.assertEqual(type(md[i]), int)
        for i in self.field_strs:
            self.assertEqual(type(md[i]), str)
        self.assertEqual(md['site'], self.site_str)

class TestFFNet(TestGetterModule, unittest.TestCase):
    getter_class = ffmirror.ffnet.FFNet
    user_test_url = 'https://www.fanfiction.net/u/5244847/Belial666'
    story_test_url = 'https://www.fanfiction.net/s/11280068/1/The-Brightest-Witch-and-the-Darkest-House'  # noqa: E501
    field_list = ['title', 'summary', 'category', 'id', 'reviews', 'chapters',
                  'words', 'characters', 'source', 'author', 'authorid',
                  'genre', 'site', 'updated', 'published', 'complete']
    field_ints = ['reviews', 'chapters', 'words']
    field_strs = ['title', 'summary', 'category', 'id', 'characters', 'source',
                  'author', 'authorid', 'genre', 'site']
    site_str = 'ffnet'
    
    def _check_valid_aid(self, aid):
        self.assertTrue(aid.isdigit())

    def _check_valid_metadata(self, md):
        super()._check_valid_metadata(md)

        cmp_dt = datetime.datetime(1998, 1, 1)  # before FFnet was started
        for i in ['published', 'updated']:
            dt = datetime.datetime.fromtimestamp(md[i])
            self.assertTrue(dt > cmp_dt)
