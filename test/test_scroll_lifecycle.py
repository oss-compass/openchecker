"""Regression tests for Elasticsearch scroll ownership and cleanup."""
import unittest
from unittest.mock import Mock, patch

from elasticsearch import Elasticsearch
from database import repo


def page(scroll_id, ids):
    return {
        '_scroll_id': scroll_id,
        'hits': {'total': {'value': 2}, 'hits': [{'_id': value} for value in ids]},
    }


class ScrollLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=Elasticsearch)
        self.client.search.return_value = page('first', ['a'])
        self.client.scroll.side_effect = [page('second', ['b']), page('last', [])]

    def test_advances_and_releases_latest_scroll_id(self):
        hits = list(repo.get_generator(self.client, {'size': 1}, index='repos'))
        self.assertEqual([hit['_id'] for hit in hits], ['a', 'b'])
        self.assertEqual(
            [call.kwargs['scroll_id'] for call in self.client.scroll.call_args_list],
            ['first', 'second'],
        )
        self.client.clear_scroll.assert_called_once_with(scroll_id='last')

    def test_explicit_close_releases_current_scroll(self):
        results = repo.get_generator(self.client, {'size': 1}, index='repos')
        self.assertEqual(next(results)['_id'], 'a')
        self.assertEqual(next(results)['_id'], 'b')
        results.close()
        self.client.clear_scroll.assert_called_once_with(scroll_id='second')

    def test_consumer_exception_releases_current_scroll(self):
        results = repo.get_generator(self.client, {'size': 1})
        next(results)
        with self.assertRaisesRegex(ValueError, 'consumer stopped'):
            results.throw(ValueError('consumer stopped'))
        self.client.clear_scroll.assert_called_once_with(scroll_id='first')

    def test_page_failure_releases_current_scroll(self):
        with patch.object(repo, 'get_items', side_effect=[page('first', ['a']), RuntimeError('failed')]):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                list(repo.get_generator(self.client, {'size': 1}))
        self.client.clear_scroll.assert_called_once_with(scroll_id='first')

    def test_empty_search_releases_context(self):
        self.client.search.return_value = page('empty', [])
        self.client.search.return_value['hits']['total'] = 0
        self.assertEqual(list(repo.get_generator(self.client, {'size': 1})), [])
        self.client.clear_scroll.assert_called_once_with(scroll_id='empty')
        self.client.scroll.assert_not_called()


if __name__ == '__main__':
    unittest.main()
