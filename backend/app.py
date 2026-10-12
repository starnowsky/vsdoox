import io
import re

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from generator import VisioGenerator, compute_layout

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

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


if __name__ == '__main__':
    app.run(debug=True, port=5000)