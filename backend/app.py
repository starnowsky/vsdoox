import io
import re
import urllib.parse

from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
from generator import VisioGenerator, compute_layout
import storage
import admin
import keycloak
import excel
from topology import analyze_interaction

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
CORS(app)

storage.init_db()
admin.init_admin_key_from_env()

# Cache-Control: HTML pages (/, /admin, /catalog) — no cache
# Static assets (/assets/*) — long-term cache with immutable
@app.after_request
def add_cache_headers(response):
    path = request.path
    if path == '/' or path == '/admin' or path == '/catalog':
        # HTML entry points: always revalidate
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif path.startswith('/assets/'):
        # Hashed assets: cache forever (Vite uses content hashes in filenames)
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

LAYOUTS = {'grid', 'horizontal', 'vertical', 'circle'}
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def _clean_title(title):
    """Убирает недопустимые для имени файла символы."""
    title = (title or '').strip()
    title = INVALID_FILENAME_CHARS.sub('_', title)
    return title or 'Схема'


def _extract_payload(data):
    """Извлекает и проверяет входные данные. Возвращает (nodes, edges, layout, title)."""
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    layout = data.get('layout', 'grid')
    title = data.get('title', 'Схема')

    if not isinstance(nodes, list) or not nodes:
        raise ValueError('Нет узлов для отображения')

    for node in nodes:
        if not isinstance(node, dict) or not str(node.get('id', '')).strip():
            raise ValueError('У каждого узла должен быть непустой id')

    if not isinstance(edges, list):
        edges = []
    for edge in edges:
        if not isinstance(edge, dict) or not edge.get('from') or not edge.get('to'):
            raise ValueError('У каждой связи должны быть поля from и to')

    if layout not in LAYOUTS:
        layout = 'grid'

    return nodes, edges, layout, _clean_title(title)


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json(silent=True) or {}
        nodes, edges, layout, title = _extract_payload(data)

        generator = VisioGenerator(title=title)
        output = generator.build(nodes, edges, layout)

        return send_file(
            io.BytesIO(output),
            mimetype='application/vnd.ms-visio.drawing',
            as_attachment=True,
            download_name=f'{title}.vsdx'
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview', methods=['POST'])
def preview():
    """Возвращает координаты для предпросмотра (SVG на клиенте)."""
    try:
        data = request.get_json(silent=True) or {}
        nodes, edges, layout, _ = _extract_payload(data)
        positions = compute_layout(nodes, edges, layout)
        return jsonify({'positions': positions})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- Проекты и топология (новый flow) ----------

@app.route('/api/projects', methods=['POST'])
def create_project():
    try:
        data = request.get_json(silent=True) or {}
        owner = data.get('owner') or data.get('owner_name')
        if not owner:
            return jsonify({'error': 'Укажите владельца (owner)'}), 400
        project_id = storage.create_project(data.get('name'), owner, data.get('group_id'))
        return jsonify({'id': project_id}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/projects', methods=['GET'])
def projects_list():
    owner = request.args.get('owner')
    if not owner:
        return jsonify({'error': 'Укажите параметр owner'}), 400
    return jsonify({'projects': storage.list_projects(owner)})


@app.route('/api/projects/<int:project_id>', methods=['GET'])
def project_get(project_id):
    data = storage.get_project(project_id)
    if data is None:
        return jsonify({'error': 'Проект не найден'}), 404
    return jsonify(data)


@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def project_save(project_id):
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    nodes = data.get('nodes', [])
    links = data.get('links', [])
    connections = data.get('connections', [])
    if not isinstance(nodes, list) or not isinstance(links, list) or not isinstance(connections, list):
        return jsonify({'error': 'nodes, links и connections должны быть списками'}), 400
    if not storage.save_project(project_id, name, nodes, links, connections):
        return jsonify({'error': 'Проект не найден'}), 404
    return jsonify({'ok': True})


@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def project_delete(project_id):
    storage.delete_project(project_id)
    return jsonify({'ok': True})


# ---------- Каталог проектов (группы доступа) ----------

def _current_identity():
    """Определяет текущего пользователя по X-User-Token / X-Admin-Token.

    Возвращает (username, is_admin) или None.
    """
    token = request.headers.get('X-User-Token') or request.headers.get('X-Admin-Token')
    if not token:
        return None
    return admin.resolve_token(token)


def _can_view(project, username, is_admin):
    if is_admin:
        return True
    if project.get('owner') == username:
        return True
    if project.get('group_id') is None:
        return True
    return storage.get_user_group_id(username) == project.get('group_id')


def _connections_rows(nodes, connections):
    """Строки таблицы связей: [источник, назначение, протокол/порт, описание]."""
    name_by_id = {str(n.get('id')): (n.get('name') or str(n.get('id'))) for n in nodes or []}
    rows = []
    for c in connections or []:
        proto = (c.get('protocol') or '')
        port = c.get('port')
        proto_port = proto + (':' + str(port) if port else '')
        rows.append([
            name_by_id.get(str(c.get('source_id')), str(c.get('source_id'))),
            name_by_id.get(str(c.get('target_id')), str(c.get('target_id'))),
            proto_port,
            c.get('description') or '',
        ])
    return rows


@app.route('/api/catalog', methods=['GET'])
def catalog_list():
    ident = _current_identity()
    if not ident:
        return jsonify({'error': 'Требуется авторизация'}), 401
    username, is_admin = ident
    folders = storage.list_catalog(username, is_admin)
    return jsonify({'folders': folders, 'viewer': username, 'is_admin': is_admin})


@app.route('/api/catalog/<int:project_id>', methods=['GET'])
def catalog_get(project_id):
    ident = _current_identity()
    if not ident:
        return jsonify({'error': 'Требуется авторизация'}), 401
    username, is_admin = ident
    project = storage.get_project(project_id)
    if project is None:
        return jsonify({'error': 'Проект не найден'}), 404
    if not _can_view(project, username, is_admin):
        return jsonify({'error': 'Нет доступа к проекту'}), 403
    return jsonify(project)


@app.route('/api/catalog/<int:project_id>', methods=['DELETE'])
def catalog_delete(project_id):
    ident = _current_identity()
    if not ident:
        return jsonify({'error': 'Требуется авторизация'}), 401
    username, is_admin = ident
    project = storage.get_project(project_id)
    if project is None:
        return jsonify({'error': 'Проект не найден'}), 404
    if not is_admin and project.get('owner') != username:
        return jsonify({'error': 'Нет прав на удаление'}), 403
    storage.delete_project(project_id)
    return jsonify({'ok': True})


@app.route('/api/objects', methods=['GET'])
def objects_list():
    ident = _current_identity()
    if not ident:
        return jsonify({'error': 'Требуется авторизация'}), 401
    username, is_admin = ident
    return jsonify({'objects': storage.list_visible_objects(username, is_admin),
                    'viewer': username, 'is_admin': is_admin})


@app.route('/api/projects/<int:project_id>/connections.xlsx', methods=['GET'])
def project_connections_xlsx(project_id):
    ident = _current_identity()
    if not ident:
        return jsonify({'error': 'Требуется авторизация'}), 401
    username, is_admin = ident
    project = storage.get_project(project_id)
    if project is None:
        return jsonify({'error': 'Проект не найден'}), 404
    if not _can_view(project, username, is_admin):
        return jsonify({'error': 'Нет доступа к проекту'}), 403
    rows = _connections_rows(project['nodes'], project['connections'])
    output = excel.build_connections_xlsx(rows)
    return send_file(
        io.BytesIO(output),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"{_clean_title(project['name'])} - связи.xlsx",
    )


@app.route('/api/admin/projects', methods=['GET'])
def admin_projects_list():
    err = _require_admin()
    if err:
        return err
    return jsonify({'projects': storage.list_visible_projects(None, is_admin=True)})


@app.route('/api/admin/projects/<int:pid>/group', methods=['PUT'])
def admin_project_group(pid):
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    gid = data.get('group_id')
    if gid in ('', 0):
        gid = None
    if not storage.set_project_group(pid, gid):
        return jsonify({'error': 'Проект не найден'}), 404
    return jsonify({'ok': True})


@app.route('/api/path', methods=['POST'])
def path_analyze():
    data = request.get_json(silent=True) or {}
    nodes = data.get('nodes', [])
    links = data.get('links', [])
    source_id = data.get('source_id')
    target_id = data.get('target_id')
    if source_id is None or target_id is None:
        return jsonify({'error': 'source_id и target_id обязательны'}), 400
    if not isinstance(nodes, list) or not isinstance(links, list):
        return jsonify({'error': 'nodes и links должны быть списками'}), 400
    for n in nodes:
        n['id'] = str(n.get('id'))
    for l in links:
        l['source_id'] = str(l.get('source_id'))
        l['target_id'] = str(l.get('target_id'))
    result = analyze_interaction(nodes, links, str(source_id), str(target_id))
    return jsonify(result)


@app.route('/api/export', methods=['POST'])
def export():
    """Экспорт графа (узлы с координатами/типами + связи) в .vsdx."""
    try:
        data = request.get_json(silent=True) or {}
        nodes = data.get('nodes', [])
        connections = data.get('connections', [])
        title = _clean_title(data.get('title') or 'Схема')

        if not isinstance(nodes, list) or not nodes:
            return jsonify({'error': 'Нет узлов для экспорта'}), 400

        generator = VisioGenerator(title=title)
        output = generator.build_graph(nodes, connections)

        return send_file(
            io.BytesIO(output),
            mimetype='application/vnd.ms-visio.drawing',
            as_attachment=True,
            download_name=f'{title}.vsdx'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/connections.xlsx', methods=['POST'])
def export_connections_xlsx():
    """Экспорт таблицы связей (источник, назначение, протокол/порт, описание) в Excel."""
    try:
        data = request.get_json(silent=True) or {}
        title = _clean_title(data.get('title') or 'Схема')
        nodes = data.get('nodes', [])
        connections = data.get('connections', [])
        if not isinstance(nodes, list) or not isinstance(connections, list):
            return jsonify({'error': 'nodes и connections должны быть списками'}), 400
        rows = _connections_rows(nodes, connections)
        output = excel.build_connections_xlsx(rows)
        return send_file(
            io.BytesIO(output),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{title} - связи.xlsx',
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ---------- Администрирование ----------

def _require_admin():
    token = request.headers.get('X-Admin-Token')
    if not token or not admin.verify_token(token):
        return jsonify({'error': 'Требуется авторизация'}), 401
    return None


@app.route('/admin')
def admin_page():
    return app.send_static_file('index.html')


@app.route('/catalog')
def catalog_page():
    return app.send_static_file('index.html')


@app.route('/api/admin/status', methods=['GET'])
def admin_status():
    return jsonify({'configured': admin.is_configured()})


@app.route('/api/admin/setup', methods=['POST'])
def admin_setup():
    try:
        data = request.get_json(silent=True) or {}
        token = admin.setup_key(data.get('key'))
        return jsonify({'token': token})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    token = admin.login(data.get('key'))
    if not token:
        return jsonify({'error': 'Неверный ключ'}), 401
    return jsonify({'token': token})


@app.route('/api/admin/keycloak', methods=['GET'])
def admin_keycloak_get():
    err = _require_admin()
    if err:
        return err
    return jsonify(admin.get_keycloak())


@app.route('/api/admin/keycloak', methods=['PUT'])
def admin_keycloak_put():
    err = _require_admin()
    if err:
        return err
    admin.save_keycloak(request.get_json(silent=True) or {})
    return jsonify({'ok': True})


@app.route('/api/admin/groups', methods=['GET'])
def admin_groups_list():
    err = _require_admin()
    if err:
        return err
    return jsonify({'groups': admin.list_groups()})


@app.route('/api/admin/groups', methods=['POST'])
def admin_groups_create():
    err = _require_admin()
    if err:
        return err
    try:
        gid = admin.create_group((request.get_json(silent=True) or {}).get('name'))
        return jsonify({'id': gid}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/groups/<int:gid>', methods=['DELETE'])
def admin_groups_delete(gid):
    err = _require_admin()
    if err:
        return err
    admin.delete_group(gid)
    return jsonify({'ok': True})


@app.route('/api/admin/users', methods=['GET'])
def admin_users_list():
    err = _require_admin()
    if err:
        return err
    return jsonify({'users': admin.list_users()})


@app.route('/api/admin/users', methods=['POST'])
def admin_users_create():
    err = _require_admin()
    if err:
        return err
    try:
        d = request.get_json(silent=True) or {}
        uid = admin.create_user(d.get('username'), d.get('password'), d.get('group_id'))
        return jsonify({'id': uid}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
def admin_users_delete(uid):
    err = _require_admin()
    if err:
        return err
    admin.delete_user(uid)
    return jsonify({'ok': True})


# ---------- Кастомные типы объектов ----------

@app.route('/api/custom-types', methods=['GET'])
def custom_types_list():
    return jsonify({'types': storage.list_custom_types()})


@app.route('/api/custom-types', methods=['POST'])
def custom_types_create():
    try:
        tid = storage.create_custom_type((request.get_json(silent=True) or {}).get('name'))
        return jsonify({'id': tid}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/custom-types/<int:tid>', methods=['DELETE'])
def custom_types_delete(tid):
    storage.delete_custom_type(tid)
    return jsonify({'ok': True})


# ---------- Авторизация (логин/пароль + Keycloak) ----------

@app.route('/api/auth/keycloak/config', methods=['GET'])
def keycloak_config():
    return jsonify(keycloak.public_config())


@app.route('/api/auth/keycloak/login')
def keycloak_login():
    if not keycloak.is_enabled():
        return jsonify({'error': 'Keycloak не настроен'}), 400
    state = keycloak.new_state()
    redirect_uri = request.host_url.rstrip('/') + '/api/auth/keycloak/callback'
    resp = redirect(keycloak.auth_url(redirect_uri, state))
    resp.set_cookie('vsdoox_oauth_state', state, httponly=True, samesite='Lax', max_age=600)
    return resp


@app.route('/api/auth/keycloak/callback')
def keycloak_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code:
        return jsonify({'error': 'Нет кода авторизации'}), 400
    if not state or state != request.cookies.get('vsdoox_oauth_state'):
        return jsonify({'error': 'Неверный state'}), 400
    redirect_uri = request.host_url.rstrip('/') + '/api/auth/keycloak/callback'
    try:
        tokens = keycloak.exchange_code(code, redirect_uri)
        access_token = tokens.get('access_token')
        if not access_token:
            raise keycloak.KeycloakError('В ответе Keycloak нет access_token')
        userinfo = keycloak.fetch_userinfo(access_token)
        username, _group = keycloak.sync_user(userinfo)
        token = admin.start_session(username)
    except keycloak.KeycloakError as e:
        return jsonify({'error': str(e)}), 400

    frontend_url = '/?kc_token=' + urllib.parse.quote(token) + '&kc_user=' + urllib.parse.quote(username)
    resp = redirect(frontend_url)
    resp.delete_cookie('vsdoox_oauth_state')
    return resp


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    token = admin.user_login(username, data.get('password'))
    if not token:
        return jsonify({'error': 'Неверный логин или пароль'}), 401
    return jsonify({'token': token, 'username': username, 'group_id': admin.get_user_group(username)})


if __name__ == '__main__':
    app.run(debug=True, port=5000)