"""Тесты ядра: топология, хранение и API.

Запуск из каталога backend:
    python tests/test_app.py
или
    python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

# Добавляем backend/ в sys.path, чтобы импортировать модули приложения.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Отдельная временная БД для тестов (до импорта app, т.к. init_db() вызывается при импорте).
_TMP = tempfile.mkdtemp(prefix='vsdoox_test_')
os.environ['VSDOOX_DB_URL'] = 'sqlite:///' + os.path.join(_TMP, 'test.db')

from topology import analyze_interaction  # noqa: E402
import app as appmod  # noqa: E402


SAMPLE_NODES = [
    {'id': 'srvA', 'type': 'server', 'name': 'Сервер A'},
    {'id': 'srvB', 'type': 'server', 'name': 'Сервер B'},
    {'id': 'net1', 'type': 'network', 'name': 'Сеть ЦОД1'},
    {'id': 'net2', 'type': 'network', 'name': 'Транзит'},
    {'id': 'net3', 'type': 'network', 'name': 'Сеть ЦОД2'},
    {'id': 'fw1', 'type': 'firewall', 'name': 'МЭ1'},
    {'id': 'fw2', 'type': 'firewall', 'name': 'МЭ2'},
    {'id': 'dc1', 'type': 'datacenter', 'name': 'ЦОД1'},
]

SAMPLE_LINKS = [
    {'source_id': 'srvA', 'target_id': 'net1'},
    {'source_id': 'net1', 'target_id': 'fw1'},
    {'source_id': 'fw1', 'target_id': 'net2'},
    {'source_id': 'net2', 'target_id': 'fw2'},
    {'source_id': 'fw2', 'target_id': 'net3'},
    {'source_id': 'net3', 'target_id': 'srvB'},
]


class TopologyTest(unittest.TestCase):
    def test_path_through_firewalls(self):
        r = analyze_interaction(SAMPLE_NODES, SAMPLE_LINKS, 'srvA', 'srvB')
        self.assertTrue(r['found'])
        self.assertEqual(r['firewalls'], ['fw1', 'fw2'])
        self.assertEqual(
            r['path'], ['srvA', 'net1', 'fw1', 'net2', 'fw2', 'net3', 'srvB']
        )

    def test_no_path_for_isolated_node(self):
        r = analyze_interaction(SAMPLE_NODES, SAMPLE_LINKS, 'srvA', 'dc1')
        self.assertFalse(r['found'])
        self.assertEqual(r['path'], [])

    def test_nested_path_through_datacenter_firewalls(self):
        nodes = [
            {'id': 'dc1', 'type': 'datacenter', 'name': 'ЦОД1', 'parent_id': None},
            {'id': 'dc2', 'type': 'datacenter', 'name': 'ЦОД2', 'parent_id': None},
            {'id': 'fw1', 'type': 'firewall', 'name': 'МЭ1', 'parent_id': 'dc1'},
            {'id': 'fw2', 'type': 'firewall', 'name': 'МЭ2', 'parent_id': 'dc2'},
            {'id': 'net1', 'type': 'network', 'name': 'Сеть1', 'parent_id': 'dc1'},
            {'id': 'net2', 'type': 'network', 'name': 'Сеть2', 'parent_id': 'dc2'},
            {'id': 'srvA', 'type': 'server', 'name': 'Сервер A', 'parent_id': 'net1'},
            {'id': 'srvB', 'type': 'server', 'name': 'Сервер B', 'parent_id': 'net2'},
        ]
        links = [{'source_id': 'fw1', 'target_id': 'fw2'}]
        r = analyze_interaction(nodes, links, 'srvA', 'srvB')
        self.assertTrue(r['found'])
        self.assertEqual(r['firewalls'], ['fw1', 'fw2'])

    def test_same_datacenter_no_firewall(self):
        nodes = [
            {'id': 'dc1', 'type': 'datacenter', 'name': 'ЦОД1', 'parent_id': None},
            {'id': 'fw1', 'type': 'firewall', 'name': 'МЭ1', 'parent_id': 'dc1'},
            {'id': 'net1', 'type': 'network', 'name': 'Сеть1', 'parent_id': 'dc1'},
            {'id': 'net2', 'type': 'network', 'name': 'Сеть2', 'parent_id': 'dc1'},
            {'id': 'srvA', 'type': 'server', 'name': 'Сервер A', 'parent_id': 'net1'},
            {'id': 'srvB', 'type': 'server', 'name': 'Сервер B', 'parent_id': 'net2'},
        ]
        links = []
        r = analyze_interaction(nodes, links, 'srvA', 'srvB')
        self.assertTrue(r['found'])
        self.assertEqual(r['firewalls'], [])


class ProjectApiTest(unittest.TestCase):
    def setUp(self):
        self.client = appmod.app.test_client()

    def test_project_lifecycle(self):
        # создание
        r = self.client.post(
            '/api/projects', json={'name': 'Схема L2', 'owner': 'alice'}
        )
        self.assertEqual(r.status_code, 201)
        pid = r.get_json()['id']

        # сохранение графа
        payload = {
            'name': 'Схема L2',
            'nodes': SAMPLE_NODES,
            'links': SAMPLE_LINKS,
            'connections': [
                {'id': 'c1', 'source_id': 'srvA', 'target_id': 'srvB',
                 'protocol': 'tcp', 'port': '443'}
            ],
        }
        r = self.client.put(f'/api/projects/{pid}', json=payload)
        self.assertEqual(r.status_code, 200)

        # чтение
        r = self.client.get(f'/api/projects/{pid}')
        self.assertEqual(r.status_code, 200)
        proj = r.get_json()
        self.assertEqual(proj['owner'], 'alice')
        self.assertEqual(len(proj['nodes']), len(SAMPLE_NODES))
        self.assertEqual(len(proj['links']), len(SAMPLE_LINKS))
        self.assertEqual(len(proj['connections']), 1)

        # удаление
        r = self.client.delete(f'/api/projects/{pid}')
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f'/api/projects/{pid}')
        self.assertEqual(r.status_code, 404)

    def test_owner_isolation(self):
        r = self.client.post('/api/projects', json={'name': 'P', 'owner': 'alice'})
        self.assertEqual(r.status_code, 201)
        r = self.client.get('/api/projects?owner=bob')
        self.assertEqual(r.get_json()['projects'], [])

    def test_path_endpoint(self):
        r = self.client.post('/api/path', json={
            'nodes': SAMPLE_NODES,
            'links': SAMPLE_LINKS,
            'source_id': 'srvA',
            'target_id': 'srvB',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['firewalls'], ['fw1', 'fw2'])

    def test_parent_id_roundtrip(self):
        r = self.client.post('/api/projects', json={'name': 'P', 'owner': 'alice'})
        pid = r.get_json()['id']
        nodes = [
            {'id': 'dc1', 'type': 'datacenter', 'name': 'ЦОД', 'parent_id': None},
            {'id': 'net1', 'type': 'network', 'name': 'Сеть', 'parent_id': 'dc1'},
            {'id': 'srv1', 'type': 'server', 'name': 'Сервер', 'parent_id': 'net1'},
        ]
        r = self.client.put(f'/api/projects/{pid}', json={
            'name': 'P', 'nodes': nodes, 'links': [], 'connections': [],
        })
        self.assertEqual(r.status_code, 200)
        proj = self.client.get(f'/api/projects/{pid}').get_json()
        by_id = {n['id']: n for n in proj['nodes']}
        self.assertEqual(by_id['net1']['parent_id'], 'dc1')
        self.assertEqual(by_id['srv1']['parent_id'], 'net1')


class LegacyExportTest(unittest.TestCase):
    """Обратная совместимость старого textarea-флоу (generate/preview)."""

    def setUp(self):
        self.client = appmod.app.test_client()

    def test_preview_and_generate(self):
        nodes = [
            {'id': 'A', 'label': 'Начало'},
            {'id': 'B', 'label': 'Обработка'},
        ]
        edges = [{'from': 'A', 'to': 'B'}]
        payload = {'nodes': nodes, 'edges': edges, 'layout': 'grid', 'title': 'T'}

        r = self.client.post('/api/preview', json=payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.get_json()['positions']), {'A', 'B'})

        r = self.client.post('/api/generate', json=payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:4], b'PK\x03\x04')

    def test_validation_errors(self):
        r = self.client.post('/api/generate', json={'nodes': []})
        self.assertEqual(r.status_code, 400)


if __name__ == '__main__':
    unittest.main()
