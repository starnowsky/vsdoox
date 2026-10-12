import io
import re

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from generator import VisioGenerator, compute_layout
import storage
from topology import analyze_interaction

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
CORS(app)

storage.init_db()

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
        project_id = storage.create_project(data.get('name'), owner)
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)