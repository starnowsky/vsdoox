from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from generator import VisioGenerator
import io
import os

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        layout = data.get('layout', 'grid')
        title = data.get('title', 'Схема')

        if not nodes:
            return jsonify({'error': 'Нет узлов для отображения'}), 400

        generator = VisioGenerator(title=title)
        output = generator.build(nodes, edges, layout)

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

@app.route('/api/preview', methods=['POST'])
def preview():
    """Возвращает координаты для предпросмотра (SVG на клиенте)."""
    from generator import compute_layout
    data = request.get_json()
    positions = compute_layout(
        data.get('nodes', []),
        data.get('edges', []),
        data.get('layout', 'grid')
    )
    return jsonify({'positions': positions})

if __name__ == '__main__':
    app.run(debug=True, port=5000)