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


class CatalogAccessTest(unittest.TestCase):
    """Каталог: видимость проектов по группам доступа."""

    def setUp(self):
        self.client = appmod.app.test_client()

    def _admin_token(self):
        r = self.client.post('/api/admin/setup', json={'key': 'secret-key'})
        if r.status_code == 201:
            return r.get_json()['token']
        r = self.client.post('/api/admin/login', json={'key': 'secret-key'})
        return r.get_json()['token']

    def _login(self, username):
        return self.client.post(
            '/api/auth/login', json={'username': username, 'password': 'p'}
        ).get_json()['token']

    def _catalog_ids(self, headers):
        data = self.client.get('/api/catalog', headers=headers).get_json()
        ids = set()
        for f in data['folders']:
            for p in f['projects']:
                ids.add(p['id'])
        return ids

    def test_group_based_visibility(self):
        admin_tok = self._admin_token()
        g1 = self.client.post('/api/admin/groups', json={'name': 'team-a'},
                              headers={'X-Admin-Token': admin_tok}).get_json()['id']
        g2 = self.client.post('/api/admin/groups', json={'name': 'team-b'},
                              headers={'X-Admin-Token': admin_tok}).get_json()['id']

        for u, g in [('u_alice', g1), ('u_bob', g1), ('u_carol', g2)]:
            self.client.post('/api/admin/users', json={'username': u, 'password': 'p', 'group_id': g},
                             headers={'X-Admin-Token': admin_tok})

        alice_tok = self._login('u_alice')
        bob_tok = self._login('u_bob')
        carol_tok = self._login('u_carol')

        # вход возвращает group_id
        r = self.client.post('/api/auth/login', json={'username': 'u_alice', 'password': 'p'})
        self.assertEqual(r.get_json()['group_id'], g1)

        # проект наследует группу владельца
        pid_alice = self.client.post('/api/projects', json={'name': 'PA', 'owner': 'u_alice'}).get_json()['id']
        pid_carol = self.client.post('/api/projects', json={'name': 'PC', 'owner': 'u_carol'}).get_json()['id']
        pa = self.client.get(f'/api/projects/{pid_alice}').get_json()
        self.assertEqual(pa['group_id'], g1)

        # члены одной группы видят проект, чужая группа — нет
        alice_ids = self._catalog_ids({'X-User-Token': alice_tok})
        bob_ids = self._catalog_ids({'X-User-Token': bob_tok})
        carol_ids = self._catalog_ids({'X-User-Token': carol_tok})
        self.assertIn(pid_alice, alice_ids)
        self.assertIn(pid_alice, bob_ids)
        self.assertNotIn(pid_alice, carol_ids)
        self.assertIn(pid_carol, carol_ids)
        self.assertNotIn(pid_carol, alice_ids)

        # админ видит всё
        admin_ids = self._catalog_ids({'X-Admin-Token': admin_tok})
        self.assertTrue({pid_alice, pid_carol}.issubset(admin_ids))

    def test_public_project_visible_to_all(self):
        admin_tok = self._admin_token()
        pid = self.client.post('/api/projects', json={'name': 'Public', 'owner': 'guest'}).get_json()['id']
        self.client.post('/api/admin/users', json={'username': 'u_viewer', 'password': 'p', 'group_id': None},
                         headers={'X-Admin-Token': admin_tok})
        viewer_tok = self._login('u_viewer')
        ids = self._catalog_ids({'X-User-Token': viewer_tok})
        self.assertIn(pid, ids)

    def test_reassign_project_group(self):
        admin_tok = self._admin_token()
        g1 = self.client.post('/api/admin/groups', json={'name': 'team-x'},
                              headers={'X-Admin-Token': admin_tok}).get_json()['id']
        pid = self.client.post('/api/projects', json={'name': 'PX', 'owner': 'u_alice'}).get_json()['id']

        # назначаем группу админом
        r = self.client.put(f'/api/admin/projects/{pid}/group', json={'group_id': g1},
                            headers={'X-Admin-Token': admin_tok})
        self.assertEqual(r.status_code, 200)
        proj = self.client.get(f'/api/projects/{pid}').get_json()
        self.assertEqual(proj['group_id'], g1)


class CatalogFoldersObjectsTest(unittest.TestCase):
    """Каталоги (папки), таблица связей (Excel) и общий каталог объектов."""

    def setUp(self):
        self.client = appmod.app.test_client()

    def _admin_token(self):
        r = self.client.post('/api/admin/setup', json={'key': 'secret-key'})
        if r.status_code == 201:
            return r.get_json()['token']
        r = self.client.post('/api/admin/login', json={'key': 'secret-key'})
        return r.get_json()['token']

    def _login(self, username):
        return self.client.post(
            '/api/auth/login', json={'username': username, 'password': 'p'}
        ).get_json()['token']

    def test_catalog_returns_folders_named_after_schema(self):
        admin_tok = self._admin_token()
        p1 = self.client.post('/api/projects', json={'name': 'Схема A', 'owner': 'u_alice'}).get_json()['id']
        p2 = self.client.post('/api/projects', json={'name': 'Схема B', 'owner': 'u_alice'}).get_json()['id']

        data = self.client.get('/api/catalog', headers={'X-Admin-Token': admin_tok}).get_json()
        folders = {f['name']: [p['id'] for p in f['projects']] for f in data['folders']}
        self.assertEqual(folders.get('Схема A'), [p1])
        self.assertEqual(folders.get('Схема B'), [p2])

    def test_folder_renamed_on_save(self):
        admin_tok = self._admin_token()
        pid = self.client.post('/api/projects', json={'name': 'Старое имя', 'owner': 'u_alice'}).get_json()['id']
        self.client.put(f'/api/projects/{pid}', json={
            'name': 'Новое имя', 'nodes': [], 'links': [], 'connections': [],
        })
        data = self.client.get('/api/catalog', headers={'X-Admin-Token': admin_tok}).get_json()
        names = [f['name'] for f in data['folders']]
        self.assertIn('Новое имя', names)
        self.assertNotIn('Старое имя', names)

    def test_save_creates_library_objects(self):
        admin_tok = self._admin_token()
        self.client.post('/api/admin/users', json={'username': 'u_lib', 'password': 'p', 'group_id': None},
                         headers={'X-Admin-Token': admin_tok})
        tok = self._login('u_lib')
        pid = self.client.post('/api/projects', json={'name': 'PLib', 'owner': 'u_lib'}).get_json()['id']
        self.client.put(f'/api/projects/{pid}', json={
            'name': 'PLib',
            'nodes': [
                {'id': 'srv1', 'type': 'server', 'name': 'Web', 'attributes': {'ip': '10.0.0.1'}},
                {'id': 'fw1', 'type': 'firewall', 'name': 'МЭ', 'attributes': {}},
            ],
            'links': [], 'connections': [],
        })
        objs = self.client.get('/api/objects', headers={'X-User-Token': tok}).get_json()['objects']
        by_name = {o['name']: o for o in objs}
        self.assertIn('Web', by_name)
        self.assertEqual(by_name['Web']['type'], 'server')
        self.assertEqual(by_name['Web']['attributes']['ip'], '10.0.0.1')
        self.assertIn('МЭ', by_name)

    def test_object_visibility_by_group(self):
        admin_tok = self._admin_token()
        g = self.client.post('/api/admin/groups', json={'name': 'lib-team'},
                             headers={'X-Admin-Token': admin_tok}).get_json()['id']
        for u in ['u_lib_a', 'u_lib_b']:
            self.client.post('/api/admin/users', json={'username': u, 'password': 'p', 'group_id': g},
                             headers={'X-Admin-Token': admin_tok})
        self.client.post('/api/admin/users', json={'username': 'u_lib_c', 'password': 'p', 'group_id': None},
                         headers={'X-Admin-Token': admin_tok})
        a_tok = self._login('u_lib_a')
        b_tok = self._login('u_lib_b')
        c_tok = self._login('u_lib_c')

        pid = self.client.post('/api/projects', json={'name': 'PLibG', 'owner': 'u_lib_a'}).get_json()['id']
        self.client.put(f'/api/projects/{pid}', json={
            'name': 'PLibG',
            'nodes': [{'id': 'n1', 'type': 'server', 'name': 'SharedObj', 'attributes': {}}],
            'links': [], 'connections': [],
        })

        names_a = {o['name'] for o in self.client.get('/api/objects', headers={'X-User-Token': a_tok}).get_json()['objects']}
        names_b = {o['name'] for o in self.client.get('/api/objects', headers={'X-User-Token': b_tok}).get_json()['objects']}
        names_c = {o['name'] for o in self.client.get('/api/objects', headers={'X-User-Token': c_tok}).get_json()['objects']}
        self.assertIn('SharedObj', names_a)
        self.assertIn('SharedObj', names_b)
        self.assertNotIn('SharedObj', names_c)

    def test_connections_xlsx_post(self):
        r = self.client.post('/api/export/connections.xlsx', json={
            'title': 'Схема',
            'nodes': [{'id': 'a', 'name': 'Сервер A'}, {'id': 'b', 'name': 'Сервер B'}],
            'connections': [{'source_id': 'a', 'target_id': 'b', 'protocol': 'tcp',
                             'port': '443', 'description': 'HTTPS'}],
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:4], b'PK\x03\x04')
        self.assertIn('spreadsheetml', r.headers.get('Content-Type', ''))

    def test_project_connections_xlsx_get(self):
        admin_tok = self._admin_token()
        self.client.post('/api/admin/users', json={'username': 'u_xlsx', 'password': 'p', 'group_id': None},
                         headers={'X-Admin-Token': admin_tok})
        tok = self._login('u_xlsx')
        pid = self.client.post('/api/projects', json={'name': 'PXlsx', 'owner': 'u_xlsx'}).get_json()['id']
        self.client.put(f'/api/projects/{pid}', json={
            'name': 'PXlsx',
            'nodes': [{'id': 'a', 'type': 'server', 'name': 'A', 'attributes': {}},
                      {'id': 'b', 'type': 'server', 'name': 'B', 'attributes': {}}],
            'links': [],
            'connections': [{'id': 'c1', 'source_id': 'a', 'target_id': 'b',
                             'protocol': 'udp', 'port': '53', 'description': 'DNS'}],
        })
        r = self.client.get(f'/api/projects/{pid}/connections.xlsx', headers={'X-User-Token': tok})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:4], b'PK\x03\x04')

    def test_description_roundtrip(self):
        pid = self.client.post('/api/projects', json={'name': 'PDesc', 'owner': 'alice'}).get_json()['id']
        self.client.put(f'/api/projects/{pid}', json={
            'name': 'PDesc',
            'nodes': [{'id': 'a', 'type': 'server', 'name': 'A', 'attributes': {}},
                      {'id': 'b', 'type': 'server', 'name': 'B', 'attributes': {}}],
            'links': [],
            'connections': [{'id': 'c1', 'source_id': 'a', 'target_id': 'b',
                             'protocol': 'tcp', 'port': '22', 'description': 'SSH доступ'}],
        })
        proj = self.client.get(f'/api/projects/{pid}').get_json()
        self.assertEqual(proj['connections'][0]['description'], 'SSH доступ')


if __name__ == '__main__':
    unittest.main()
