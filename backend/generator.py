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
XML_NS = 'http://www.w3.org/XML/1998/namespace'

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
    row = etree.Element('Row', T=etype, IX=str(ix))
    for c in cells:
        row.append(c)
    return row


def _section(name, rows):
    section = etree.Element('Section', N=name)
    for r in rows:
        section.append(r)
    return section


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
        cp_section = etree.Element('Section', N='Connection Points')
        for r in cp_rows:
            cp_section.append(r)
        shape.append(cp_section)

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
    def __init__(self, title='Схема'):
        self.title = title

    def build(self, nodes, edges, layout='grid'):
        positions = compute_layout(nodes, edges, layout)
        return self._build_package(nodes, edges, positions, PAGE_W, PAGE_H,
                                   graph_format=False)

    def build_graph(self, nodes, connections):
        SCALE = 100.0
        positions = {}
        for node in nodes:
            nid = node['id']
            t = node.get('type', 'server')
            default = TYPE_STYLE.get(t, TYPE_STYLE['server'])
            w = float(node.get('w') or default['w'])
            h = float(node.get('h') or default['h'])
            positions[nid] = {
                'x': float(node.get('x') or 0),
                'y': float(node.get('y') or 0),
                'w': w,
                'h': h,
            }
        margin = 60.0
        if positions:
            min_x = min(p['x'] for p in positions.values())
            min_y = min(p['y'] for p in positions.values())
            max_x = max(p['x'] + p['w'] for p in positions.values())
            max_y = max(p['y'] + p['h'] for p in positions.values())
        else:
            min_x = min_y = 0.0
            max_x = max_y = 1000.0
        page_w = round(max(8.5, (max_x - min_x + 2 * margin) / SCALE), 2)
        page_h = round(max(11.0, (max_y - min_y + 2 * margin) / SCALE), 2)
        visio_pos = {}
        for nid, p in positions.items():
            x_in = (p['x'] - min_x + margin) / SCALE
            y_top = (p['y'] - min_y + margin) / SCALE
            y_in = page_h - y_top - p['h'] / SCALE
            visio_pos[nid] = {
                'x': round(x_in, 3), 'y': round(y_in, 3),
                'w': round(p['w'] / SCALE, 3), 'h': round(p['h'] / SCALE, 3),
            }
        return self._build_package(nodes, connections, visio_pos,
                                   page_w, page_h, graph_format=True)

    def _build_package(self, nodes, connections, positions, page_w, page_h,
                       graph_format):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', self._content_types())
            z.writestr('_rels/.rels', self._root_rels())
            z.writestr('docProps/core.xml', self._core_props_xml())
            z.writestr('docProps/app.xml', self._app_props_xml())
            z.writestr('visio/document.xml', self._document_xml())
            z.writestr('visio/_rels/document.xml.rels', self._document_rels())
            z.writestr('visio/pages/pages.xml', self._pages_xml(page_w, page_h))
            z.writestr('visio/pages/_rels/pages.xml.rels', self._pages_rels())
            z.writestr('visio/pages/page1.xml',
                       self._page_xml(nodes, connections, positions,
                                      graph_format))
            z.writestr('visio/masters/masters.xml', self._masters_xml())
            z.writestr('visio/masters/_rels/masters.xml.rels',
                       self._masters_rels())
            z.writestr('visio/windows.xml', self._windows_xml())
        buf.seek(0)
        return buf.read()

    def _content_types(self):
        root = etree.Element('Types', xmlns=CT_NS)
        for ext, ct in [
            ('rels', 'application/vnd.openxmlformats-package.relationships+xml'),
            ('xml', 'application/xml'),
        ]:
            etree.SubElement(root, 'Default', Extension=ext, ContentType=ct)
        for part, ct in [
            ('/visio/document.xml', 'application/vnd.ms-visio.drawing.main+xml'),
            ('/visio/pages/pages.xml', 'application/vnd.ms-visio.pages+xml'),
            ('/visio/pages/page1.xml', 'application/vnd.ms-visio.page+xml'),
            ('/visio/masters/masters.xml', 'application/vnd.ms-visio.masters+xml'),
            ('/visio/windows.xml', 'application/vnd.ms-visio.windows+xml'),
            ('/docProps/core.xml', 'application/vnd.openxmlformats-package.core-properties+xml'),
            ('/docProps/app.xml', 'application/vnd.openxmlformats-officedocument.extended-properties+xml'),
        ]:
            etree.SubElement(root, 'Override', PartName=part, ContentType=ct)
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _root_rels(self):
        root = etree.Element('Relationships',
                             xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        rels = [
            ('rId1', 'http://schemas.microsoft.com/visio/2010/relationships/document',
             'visio/document.xml'),
            ('rId2', 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties',
             'docProps/core.xml'),
            ('rId3', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties',
             'docProps/app.xml'),
        ]
        for rid, reltype, target in rels:
            etree.SubElement(root, 'Relationship', Id=rid, Type=reltype,
                             Target=target)
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _document_rels(self):
        root = etree.Element('Relationships',
                             xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        rels = [
            ('rId1', 'http://schemas.microsoft.com/visio/2010/relationships/pages',
             'pages/pages.xml'),
            ('rId2', 'http://schemas.microsoft.com/visio/2010/relationships/windows',
             'windows.xml'),
            ('rId3', 'http://schemas.microsoft.com/visio/2010/relationships/masters',
             'masters/masters.xml'),
        ]
        for rid, reltype, target in rels:
            etree.SubElement(root, 'Relationship', Id=rid, Type=reltype,
                             Target=target)
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _document_xml(self):
        root = etree.Element('VisioDocument', xmlns=VISIO_NS,
                             **{'{%s}space' % XML_NS: 'preserve'})
        etree.SubElement(root, 'DocumentSettings', TopPage='0',
                         DefaultTextStyle='0', DefaultLineStyle='0',
                         DefaultFillStyle='0')
        etree.SubElement(root, 'Colors')
        etree.SubElement(root, 'FaceNames')
        etree.SubElement(root, 'StyleSheets')
        sheet = etree.SubElement(root, 'DocumentSheet', NameU='TheDoc',
                                 LineStyle='0', FillStyle='0', TextStyle='0')
        etree.SubElement(sheet, 'Shapes')
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _masters_xml(self):
        root = etree.Element('Masters', xmlns=VISIO_NS,
                             **{'{%s}space' % XML_NS: 'preserve'})
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _masters_rels(self):
        root = etree.Element('Relationships',
                             xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _windows_xml(self):
        root = etree.Element('Windows', xmlns=VISIO_NS,
                             **{'{%s}space' % XML_NS: 'preserve'})
        etree.SubElement(root, 'Window', ID='0', WindowType='Drawing',
                         WindowState='1073741824', WindowLeftX='0',
                         WindowTopY='0', WindowWidth='1239', WindowHeight='846',
                         ContainerType='Page', Page='0', ViewScale='1',
                         ViewCenterX='5.5', ViewCenterY='4.25')
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _app_props_xml(self):
        root = etree.Element('{%s}Properties' % EXT_PROPS_NS,
                             nsmap={'vt': VT_NS})
        app = etree.SubElement(root, '{%s}Application' % EXT_PROPS_NS)
        app.text = 'Microsoft Visio'
        ver = etree.SubElement(root, '{%s}AppVersion' % EXT_PROPS_NS)
        ver.text = '16.0000'
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _core_props_xml(self):
        title = _xml_escape(self.title or 'Схема')
        root = etree.Element('{%s}coreProperties' % CORE_PROPS_NS,
                             nsmap={'cp': CORE_PROPS_NS, 'dc': DC_NS,
                                    'dcterms': DCTERMS_NS, 'xsi': XSI_NS})
        dc_title = etree.SubElement(root, '{%s}title' % DC_NS)
        dc_title.text = title
        etree.SubElement(root, '{%s}creator' % DC_NS).text = 'vsdoox'
        lm = etree.SubElement(root, '{%s}lastModifiedBy' % CORE_PROPS_NS)
        lm.text = 'vsdoox'
        created = etree.SubElement(root, '{%s}created' % DCTERMS_NS,
                                   **{'{%s}type' % XSI_NS: 'dcterms:W3CDTF'})
        created.text = '2024-01-01T00:00:00Z'
        modified = etree.SubElement(root, '{%s}modified' % DCTERMS_NS,
                                    **{'{%s}type' % XSI_NS: 'dcterms:W3CDTF'})
        modified.text = '2024-01-01T00:00:00Z'
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _pages_xml(self, page_w, page_h):
        page_name = _xml_escape(self.title or 'Page-1')
        root = etree.Element('Pages', xmlns=VISIO_NS,
                             **{'{%s}space' % XML_NS: 'preserve'})
        page = etree.SubElement(root, 'Page', ID='0', NameU=page_name,
                                Name=page_name, ViewScale='1',
                                ViewCenterX=str(page_w / 2),
                                ViewCenterY=str(page_h / 2))
        sheet = etree.SubElement(page, 'PageSheet', LineStyle='0',
                                 FillStyle='0', TextStyle='0')
        etree.SubElement(sheet, 'Cell', N='PageWidth', V=str(page_w))
        etree.SubElement(sheet, 'Cell', N='PageHeight', V=str(page_h))
        etree.SubElement(sheet, 'Cell', N='PageScale', V='1')
        etree.SubElement(sheet, 'Cell', N='DrawingScale', V='1')
        etree.SubElement(page, 'Rel', **{f'{{{REL_NS}}}id': 'rId1'})
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _page_xml(self, nodes, connections, positions, graph_format):
        shapes = []
        shape_id = 1
        node_to_sheet = {}  # логический id узла -> ссылка ThePage!Sheet.<ID формы>

        for node in nodes:
            nid = node['id']
            if nid not in positions:
                continue
            node_to_sheet[nid] = f'Sheet.{shape_id}'
            shape = self._node_shape(shape_id, node, positions[nid],
                                     graph_format=graph_format)
            shapes.append(shape)
            shape_id += 1

        for conn in connections:
            if graph_format:
                s = conn.get('source_id')
                t = conn.get('target_id')
                label = conn.get('protocol') or 'any'
                if conn.get('port'):
                    label += chr(92) + str(conn.get('port'))
                color = conn.get('color')
            else:
                s = conn.get('from')
                t = conn.get('to')
                label = conn.get('label', '')
                color = conn.get('color', '#666666')

            if s not in positions or t not in positions:
                continue
            shape = self._connector_shape(shape_id, positions[s], positions[t],
                                          label, color,
                                          node_to_sheet[s], node_to_sheet[t],
                                          graph_format=graph_format)
            shapes.append(shape)
            shape_id += 1

        root = etree.Element('PageContents', xmlns=VISIO_NS,
                             **{'{%s}space' % XML_NS: 'preserve'})
        shapes_el = etree.SubElement(root, 'Shapes')
        for sh in shapes:
            shapes_el.append(sh)
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

    def _node_shape(self, sid, node, pos, graph_format=False):
        x, y, w, h = pos['x'], pos['y'], pos['w'], pos['h']
        pin_x = x + w / 2
        pin_y = y + h / 2

        if graph_format:
            t = node.get('type', 'server')
            style = TYPE_STYLE.get(t, TYPE_STYLE['server'])
            fill = style['fill']
            border = style['border']
            text = _xml_escape(_node_label(node))
        else:
            fill = _safe_color(node.get('color'), '#DAE8FC')
            border = _safe_color(node.get('border'), '#6C8EBF')
            text = _xml_escape(node.get('label') or node.get('id') or '')

        # Connection points только по бокам: левый центр (X1/Y1) и правый центр (X2/Y2).
        # Верх/низ не используются — линии соединяются только сбоку.
        # Локальная СК Visio: начало в левом нижнем углу, ось Y вверх;
        # pin = центр формы, LocPin = (w/2, h/2).
        cp = [(0.0, round(h / 2, 3), 0), (round(w, 3), round(h / 2, 3), 0)]

        return _shape(sid, f'Node{sid}', pin_x, pin_y, w, h,
                      text=text, fill=fill, border=border,
                      connection_points=cp)

    def _connector_shape(self, sid, from_pos, to_pos, label, color,
                         source_sheet, target_sheet, graph_format=False):
        # Соединяемся только по бокам (left/right).
        # Если цель справа (или на том же x) — источник использует правый бок,
        # цель — левый. Иначе — источник левый бок, цель — правый.
        target_is_right = to_pos['x'] >= from_pos['x']

        if target_is_right:
            src_x = from_pos['x'] + from_pos['w']
            src_y = from_pos['y'] + from_pos['h'] / 2
            tgt_x = to_pos['x']
            tgt_y = to_pos['y'] + to_pos['h'] / 2
            begin_conn = 'X2'  # правая точка источника (IX=2)
            end_conn = 'X1'    # левая точка цели (IX=1)
        else:
            src_x = from_pos['x']
            src_y = from_pos['y'] + from_pos['h'] / 2
            tgt_x = to_pos['x'] + to_pos['w']
            tgt_y = to_pos['y'] + to_pos['h'] / 2
            begin_conn = 'X1'  # левая точка источника (IX=1)
            end_conn = 'X2'    # правая точка цели (IX=2)

        conn_y = {'X1': 'Y1', 'X2': 'Y2'}

        # Ортогональный путь: прямая линия, если по уровню на одной высоте,
        # иначе Z-образный через среднюю по X точку.
        pts = [(src_x, src_y)]
        if src_y != tgt_y:
            mid_x = (src_x + tgt_x) / 2
            pts.append((round(mid_x, 3), src_y))
            pts.append((round(mid_x, 3), tgt_y))
        pts.append((tgt_x, tgt_y))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pin_x = (min(xs) + max(xs)) / 2
        pin_y = (min(ys) + max(ys)) / 2
        w = max(max(xs) - min(xs), 0.001)
        h = max(max(ys) - min(ys), 0.001)

        local_pts = [
            (round(px - (pin_x - w / 2), 3), round(py - (pin_y - h / 2), 3))
            for px, py in pts
        ]

        geometry_rows = _connector_geometry_rows(local_pts)

        line_color = _safe_color(color, '#666666')

        # source_sheet/target_sheet уже имеют вид 'Sheet.<N>', где N — ID фигуры узла на странице.
        # Ссылка на ячейку Connection Points другой фигуры — классический способ приклеить конец
        # коннектора к точке подключения (Visio сама приводит системы координат фигур).
        extra_cells = [
            _cell('BeginX', f'ThePage!{source_sheet}!Connections.{begin_conn}'),
            _cell('BeginY', f'ThePage!{source_sheet}!Connections.{conn_y[begin_conn]}'),
            _cell('EndX', f'ThePage!{target_sheet}!Connections.{end_conn}'),
            _cell('EndY', f'ThePage!{target_sheet}!Connections.{conn_y[end_conn]}'),
        ]

        return _shape(sid, f'Connector{sid}', pin_x, pin_y, w, h,
                      text=label if label else '',
                      line_color=line_color, end_arrow=4,
                      geometry_rows=geometry_rows,
                      extra_cells=extra_cells,
                      char_size='0.125', char_color=line_color)

    def _pages_rels(self):
        root = etree.Element('Relationships',
                             xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        etree.SubElement(root, 'Relationship', Id='rId1',
                         Type='http://schemas.microsoft.com/visio/2010/relationships/page',
                         Target='page1.xml')
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                              standalone=True)
