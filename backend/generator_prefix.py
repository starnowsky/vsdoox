import io
import math
import re
from lxml import etree

# Размеры страницы (в дюймах, Visio использует дюймы)
PAGE_W = 11.0
PAGE_H = 8.5

NODE_W = 1.5
NODE_H = 0.75

MARGIN_X = 1.0
MARGIN_Y = 1.0

# Отступ «хвоста» коннектора ниже нижней грани узла (дюймы, 30 px при 100 px/дюйм)
STUB_INCHES = 30.0 / 100.0

HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')

VISIO_NS = 'http://schemas.microsoft.com/office/visio/2012/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
CORE_PROPS_NS = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
DC_NS = 'http://purl.org/dc/elements/1.1/'
DCTERMS_NS = 'http://purl.org/dc/terms/'
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'
EXT_PROPS_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
VT_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'

NSMAP = {
    None: VISIO_NS,
    'r': REL_NS,
    'cp': CORE_PROPS_NS,
    'dc': DC_NS,
    'dcterms': DCTERMS_NS,
    'xsi': XSI_NS,
    'vt': VT_NS,
}


def _xml_escape(value):
    """Экранирует спецсимволы для вставки текста в XML."""
    return (str(value)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _safe_color(value, default):
    """Возвращает валидный HEX-цвет либо значение по умолчанию."""
    if isinstance(value, str) and HEX_COLOR_RE.fullmatch(value):
        return value
    return default


TYPE_STYLE = {
    'datacenter': {'fill': '#F3F4F6', 'border': '#9CA3AF', 'w': 300, 'h': 200},
    'network': {'fill': '#ECFDF5', 'border': '#10B981', 'w': 272, 'h': 100},
    'server': {'fill': '#EEF4FF', 'border': '#3B82F6', 'w': 130, 'h': 48},
    'firewall': {'fill': '#FEF2F2', 'border': '#EF4444', 'w': 110, 'h': 200},
}


def _node_label(node):
    """Текст подписи узла в зависимости от типа."""
    t = node.get('type', 'server')
    name = node.get('name') or node.get('id') or ''
    attrs = node.get('attributes') or {}
    if t == 'datacenter':
        return 'ЦОД — ' + name
    if t == 'server' and attrs.get('ip'):
        return name + ' · ' + str(attrs['ip'])
    if t == 'network':
        parts = []
        if attrs.get('cidr'):
            parts.append(str(attrs['cidr']))
        if attrs.get('vlan'):
            parts.append('VLAN ' + str(attrs['vlan']))
        if parts:
            return name + ' · ' + ' · '.join(parts)
    return name


# ---------- Вспомогательные конструкторы XML через lxml ----------

def _cell(name, val):
    return etree.Element('Cell', N=name, V=str(val))


def _row(etype, ix, cells):
    return etree.Element('Row', T=etype, IX=str(ix), *[c for c in cells])


def _section(name, rows):
    return etree.Element('Section', N=name, *[r for r in rows])


def _shape(sid, name_u, pin_x, pin_y, w, h, text='', fill=None, border=None,
           char_size='0.1667', char_color='#333333', line_weight='0.015',
           end_arrow=None, line_color=None, geometry_rows=None,
           connection_points=None, extra_cells=None):
    """Собирает <Shape> со всеми разделами Visio."""
    attrs = {
        'ID': str(sid),
        'NameU': name_u,
        'Type': 'Shape',
        'LineStyle': '0',
        'FillStyle': '0',
        'TextStyle': '0',
    }
    shape = etree.Element('Shape', **attrs)

    cells = [
        _cell('PinX', round(pin_x, 3)),
        _cell('PinY', round(pin_y, 3)),
        _cell('Width', round(w, 3)),
        _cell('Height', round(h, 3)),
        _cell('LocPinX', round(w / 2, 3)),
        _cell('LocPinY', round(h / 2, 3)),
        _cell('Angle', 0),
        _cell('FlipX', 0),
        _cell('FlipY', 0),
        _cell('ResizeMode', 0),
    ]
    if extra_cells:
        cells.extend(extra_cells)

    # Основной раздел ячеек (без Section N — прямой список Cell в Shape)
    for c in cells:
        shape.append(c)

    if geometry_rows:
        shape.append(_section('Geometry', geometry_rows))

    if connection_points:
        cp_rows = []
        for i, (cx, cy, ctype) in enumerate(connection_points, start=1):
            cp_rows.append(_row('X', i, [_cell('X', round(cx, 3)),
                                         _cell('Y', round(cy, 3)),
                                         _cell('Type', ctype)]))
        shape.append(etree.Element('Section', N='Connection Points', *cp_rows))

    if fill is not None:
        shape.append(_section('Fill', [
            _cell('FillForegnd', fill),
            _cell('FillBkgnd', fill),
            _cell('FillPattern', 1),
        ]))

    if border is not None or line_color is not None:
        line_cells = []
        if border is not None:
            line_cells.append(_cell('LineColor', border))
        if line_color is not None:
            line_cells.append(_cell('LineColor', line_color))
        line_cells.append(_cell('LineWeight', line_weight))
        if end_arrow is not None:
            line_cells.append(_cell('EndArrow', end_arrow))
        shape.append(_section('Line', line_cells))

    shape.append(_section('Character', [
        _cell('Size', char_size),
        _cell('Color', char_color),
    ]))

    if text:
        text_el = etree.Element('Text')
        text_el.text = _xml_escape(text)
        shape.append(text_el)

    return shape


def _connector_geometry_rows(points):
    """Геометрия ортогонального коннектора: список (x, y) точек в локальных coords."""
    rows = []
    for i, (x, y) in enumerate(points):
        etype = 'MoveTo' if i == 0 else 'LineTo'
        rows.append(_row(etype, i + 1, [_cell('X', round(x, 3)), _cell('Y', round(y, 3))]))
    return rows


def compute_layout(nodes, edges, layout='grid'):
    """Вычисляет координаты узлов. Возвращает dict {id: {x, y, w, h}}."""
    positions = {}
    n = len(nodes)

    if layout == 'grid':
        cols = max(1, int(math.ceil(math.sqrt(n))))
        rows = int(math.ceil(n / cols))
        cell_w = (PAGE_W - 2 * MARGIN_X) / cols
        cell_h = (PAGE_H - 2 * MARGIN_Y) / rows

        for i, node in enumerate(nodes):
            row = i // cols
            col = i % cols
            x = MARGIN_X + col * cell_w + (cell_w - NODE_W) / 2
            # Visio: Y снизу вверх
            y_top = MARGIN_Y + row * cell_h + (cell_h - NODE_H) / 2
            y = PAGE_H - y_top - NODE_H
            positions[node['id']] = {
                'x': round(x, 3),
                'y': round(y, 3),
                'w': NODE_W,
                'h': NODE_H,
            }
    elif layout == 'horizontal':
        gap = 0.6
        total_w = n * NODE_W + (n - 1) * gap
        start_x = max(MARGIN_X, (PAGE_W - total_w) / 2)
        y = (PAGE_H - NODE_H) / 2
        for i, node in enumerate(nodes):
            x = start_x + i * (NODE_W + gap)
            positions[node['id']] = {
                'x': round(x, 3),
                'y': round(y, 3),
                'w': NODE_W,
                'h': NODE_H,
            }
    elif layout == 'vertical':
        gap = 0.6
        total_h = n * NODE_H + (n - 1) * gap
        start_y_top = max(MARGIN_Y, (PAGE_H - total_h) / 2)
        x = (PAGE_W - NODE_W) / 2
        for i, node in enumerate(nodes):
            y_top = start_y_top + i * (NODE_H + gap)
            y = PAGE_H - y_top - NODE_H
            positions[node['id']] = {
                'x': round(x, 3),
                'y': round(y, 3),
                'w': NODE_W,
                'h': NODE_H,
            }
    else:  # circle
        cx, cy = PAGE_W / 2, PAGE_H / 2
        radius = min(PAGE_W, PAGE_H) / 2 - MARGIN_X - max(NODE_W, NODE_H)
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / max(1, n)
            x = cx + radius * math.cos(angle) - NODE_W / 2
            y = cy + radius * math.sin(angle) - NODE_H / 2
            positions[node['id']] = {
                'x': round(x, 3),
                'y': round(y, 3),
                'w': NODE_W,
                'h': NODE_H,
            }

    return positions


class VisioGenerator:
