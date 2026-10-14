import io
import math
import re

# Размеры страницы (в дюймах, Visio использует дюймы)
PAGE_W = 11.0
PAGE_H = 8.5

NODE_W = 1.5
NODE_H = 0.75

MARGIN_X = 1.0
MARGIN_Y = 1.0

HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


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
    if t == 'network' and attrs.get('cidr'):
        return name + ' · ' + str(attrs['cidr'])
    return name


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

        # Собираем минимальный .vsdx вручную: VSDX — это ZIP-контейнер (OPC)
        # с XML-частями (document, pages, page1 и их relationships).
        import zipfile
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            # [Content_Types].xml
            z.writestr('[Content_Types].xml', self._content_types())

            # _rels/.rels
            z.writestr('_rels/.rels', self._root_rels())

            # docProps (обязательные для открытия в Visio)
            z.writestr('docProps/core.xml', self._core_props_xml())
            z.writestr('docProps/app.xml', self._app_props_xml())

            # visio/document.xml
            z.writestr('visio/document.xml', self._document_xml())

            # visio/_rels/document.xml.rels
            z.writestr('visio/_rels/document.xml.rels', self._document_rels())

            # visio/pages/pages.xml
            z.writestr('visio/pages/pages.xml', self._pages_xml())

            # visio/pages/_rels/pages.xml.rels
            z.writestr('visio/pages/_rels/pages.xml.rels',
                       self._pages_rels())

            # visio/pages/page1.xml
            z.writestr('visio/pages/page1.xml',
                       self._page_xml(nodes, edges, positions))
            z.writestr('visio/masters/masters.xml', self._masters_xml())
            z.writestr('visio/masters/_rels/masters.xml.rels', self._masters_rels())
            z.writestr('visio/windows.xml', self._windows_xml())

        buf.seek(0)
        return buf.read()

    # ---------- Шаблоны XML ----------

    def _content_types(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
  <Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
  <Override PartName="/visio/masters/masters.xml" ContentType="application/vnd.ms-visio.masters+xml"/>
  <Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

    def _root_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

    def _document_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
  <Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
  <Relationship Id="rId3" Type="http://schemas.microsoft.com/visio/2010/relationships/masters" Target="masters/masters.xml"/>
</Relationships>'''

    def _pages_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>'''

    def _document_xml(self):
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve">
  <DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" DefaultFillStyle="0"/>
  <Colors/>
  <FaceNames/>
  <StyleSheets/>
  <DocumentSheet NameU="TheDoc" LineStyle="0" FillStyle="0" TextStyle="0">
    <Shapes/>
  </DocumentSheet>
</VisioDocument>'''

    def _masters_xml(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
</Masters>'''

    def _masters_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>'''

    def _windows_xml(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Windows xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve" ClientWidth="1239" ClientHeight="846" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <Window ID="0" WindowType="Drawing" WindowState="1073741824" WindowLeftX="0" WindowTopY="0" WindowWidth="1239" WindowHeight="846" ContainerType="Page" Page="0" ViewScale="1" ViewCenterX="5.5" ViewCenterY="4.25"/>
</Windows>'''

    def _pages_xml(self):
        page_name = _xml_escape(self.title or 'Page-1')
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve">
  <Page ID="0" NameU="{page_name}" Name="{page_name}" ViewScale="1" ViewCenterX="5.5" ViewCenterY="4.25">
    <PageSheet LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PageWidth" V="11"/>
      <Cell N="PageHeight" V="8.5"/>
      <Cell N="PageScale" V="1"/>
      <Cell N="DrawingScale" V="1"/>
    </PageSheet>
    <Rel r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
  </Page>
</Pages>'''

    def _page_xml(self, nodes, edges, positions):
        shapes_xml = []
        shape_id = 1

        # Сначала узлы
        for node in nodes:
            pos = positions[node['id']]
            xml = self._shape_to_xml(shape_id, node, pos)
            shapes_xml.append(xml)
            shape_id += 1

        # Затем соединители
        for edge in edges:
            from_id = edge.get('from')
            to_id = edge.get('to')
            if from_id not in positions or to_id not in positions:
                continue
            xml = self._connector_to_xml(
                shape_id, positions[from_id], positions[to_id]
            )
            shapes_xml.append(xml)
            shape_id += 1

        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xml:space="preserve">
  <Shapes>
    {''.join(shapes_xml)}
  </Shapes>
</PageContents>'''

    def _shape_to_xml(self, sid, node, pos):
        x, y, w, h = pos['x'], pos['y'], pos['w'], pos['h']
        pin_x = x + w / 2
        pin_y = y + h / 2
        text = _xml_escape(node.get('label') or node.get('id') or '')
        fill = _safe_color(node.get('color'), '#DAE8FC')
        border = _safe_color(node.get('border'), '#6C8EBF')

        return f'''<Shape ID="{sid}" NameU="Node{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{w}"/>
      <Cell N="Height" V="{h}"/>
      <Cell N="LocPinX" V="{w/2}"/>
      <Cell N="LocPinY" V="{h/2}"/>
      <Cell N="Angle" V="0"/>
      <Cell N="FlipX" V="0"/>
      <Cell N="FlipY" V="0"/>
      <Cell N="ResizeMode" V="0"/>
      <Section N="Fill">
        <Cell N="FillForegnd" V="{fill}"/>
        <Cell N="FillBkgnd" V="{fill}"/>
        <Cell N="FillPattern" V="1"/>
      </Section>
      <Section N="Line">
        <Cell N="LineColor" V="{border}"/>
        <Cell N="LineWeight" V="0.015"/>
        <Cell N="Rounding" V="0.1"/>
      </Section>
      <Section N="Character">
        <Cell N="Size" V="0.1667"/>
        <Cell N="Color" V="#333333"/>
      </Section>
      <Text>{text}</Text>
    </Shape>'''

    def _connector_to_xml(self, sid, from_pos, to_pos):
        x1 = from_pos['x'] + from_pos['w'] / 2
        y1 = from_pos['y'] + from_pos['h'] / 2
        x2 = to_pos['x'] + to_pos['w'] / 2
        y2 = to_pos['y'] + to_pos['h'] / 2

        def clip(px, py, qx, qy, w, h):
            dx = qx - px
            dy = qy - py
            if dx == 0 and dy == 0:
                return px, py
            tx = (w / 2) / abs(dx) if dx != 0 else float('inf')
            ty = (h / 2) / abs(dy) if dy != 0 else float('inf')
            t = min(tx, ty)
            return px + dx * t, py + dy * t

        cx1, cy1 = clip(x1, y1, x2, y2, from_pos['w'], from_pos['h'])
        cx2, cy2 = clip(x2, y2, x1, y1, to_pos['w'], to_pos['h'])

        # Локальные координаты относительно PinX/PinY
        pin_x = (cx1 + cx2) / 2
        pin_y = (cy1 + cy2) / 2
        w = abs(cx2 - cx1)
        h = abs(cy2 - cy1)
        w = max(w, 0.001)
        h = max(h, 0.001)

        # Локальные координаты начала и конца
        lx1 = cx1 - (pin_x - w / 2)
        ly1 = cy1 - (pin_y - h / 2)
        lx2 = cx2 - (pin_x - w / 2)
        ly2 = cy2 - (pin_y - h / 2)

        return f'''<Shape ID="{sid}" NameU="Connector{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{w}"/>
      <Cell N="Height" V="{h}"/>
      <Cell N="LocPinX" V="{w/2}"/>
      <Cell N="LocPinY" V="{h/2}"/>
      <Cell N="Angle" V="0"/>
      <Section N="Geometry" IX="0">
        <Row T="MoveTo" IX="1">
          <Cell N="X" V="{lx1}"/>
          <Cell N="Y" V="{ly1}"/>
        </Row>
        <Row T="LineTo" IX="2">
          <Cell N="X" V="{lx2}"/>
          <Cell N="Y" V="{ly2}"/>
        </Row>
      </Section>
      <Section N="Line">
        <Cell N="LineColor" V="#666666"/>
        <Cell N="LineWeight" V="0.015"/>
        <Cell N="EndArrow" V="4"/>
      </Section>
    </Shape>'''
    def _app_props_xml(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Visio</Application>
  <AppVersion>16.0000</AppVersion>
</Properties>'''

    def _core_props_xml(self):
        title = _xml_escape(self.title or 'Схема')
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{title}</dc:title>
  <dc:creator>vsdoox</dc:creator>
  <cp:lastModifiedBy>vsdoox</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2024-01-01T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2024-01-01T00:00:00Z</dcterms:modified>
</cp:coreProperties>'''

    # ---------- Экспорт графа (новый формат) ----------

    def build_graph(self, nodes, connections):
        """Экспорт графа (узлы с координатами/типами + связи) в .vsdx."""
        SCALE = 100.0  # px на дюйм
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
                'x': round(x_in, 3),
                'y': round(y_in, 3),
                'w': round(p['w'] / SCALE, 3),
                'h': round(p['h'] / SCALE, 3),
            }

        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', self._content_types())
            z.writestr('_rels/.rels', self._root_rels())
            z.writestr('docProps/core.xml', self._core_props_xml())
            z.writestr('docProps/app.xml', self._app_props_xml())
            z.writestr('visio/document.xml', self._document_xml())
            z.writestr('visio/_rels/document.xml.rels', self._document_rels())
            z.writestr('visio/pages/pages.xml', self._pages_xml_sized(page_w, page_h))
            z.writestr('visio/pages/_rels/pages.xml.rels', self._pages_rels())
            z.writestr('visio/pages/page1.xml',
                       self._graph_page_xml(nodes, connections, visio_pos))
            z.writestr('visio/masters/masters.xml', self._masters_xml())
            z.writestr('visio/masters/_rels/masters.xml.rels', self._masters_rels())
            z.writestr('visio/windows.xml', self._windows_xml())
        buf.seek(0)
        return buf.read()

    def _pages_xml_sized(self, page_w, page_h):
        page_name = _xml_escape(self.title or 'Page-1')
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve">
  <Page ID="0" NameU="{page_name}" Name="{page_name}" ViewScale="1" ViewCenterX="{page_w / 2}" ViewCenterY="{page_h / 2}">
    <PageSheet LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PageWidth" V="{page_w}"/>
      <Cell N="PageHeight" V="{page_h}"/>
      <Cell N="PageScale" V="1"/>
      <Cell N="DrawingScale" V="1"/>
    </PageSheet>
    <Rel r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
  </Page>
</Pages>'''

    def _graph_page_xml(self, nodes, connections, positions):
        shapes_xml = []
        shape_id = 1
        for node in nodes:
            nid = node['id']
            if nid not in positions:
                continue
            shapes_xml.append(self._graph_shape_xml(shape_id, node, positions[nid]))
            shape_id += 1
        for conn in connections:
            s = conn.get('source_id')
            t = conn.get('target_id')
            if s not in positions or t not in positions:
                continue
            label = conn.get('protocol') or 'any'
            if conn.get('port'):
                label += ':' + str(conn.get('port'))
            shapes_xml.append(self._graph_connector_xml(
                shape_id, positions[s], positions[t], label, conn.get('color')))
            shape_id += 1
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xml:space="preserve">
  <Shapes>
    {''.join(shapes_xml)}
  </Shapes>
</PageContents>'''

    def _graph_shape_xml(self, sid, node, pos):
        x, y, w, h = pos['x'], pos['y'], pos['w'], pos['h']
        pin_x = x + w / 2
        pin_y = y + h / 2
        t = node.get('type', 'server')
        style = TYPE_STYLE.get(t, TYPE_STYLE['server'])
        fill = style['fill']
        border = style['border']
        text = _xml_escape(_node_label(node))
        return f'''<Shape ID="{sid}" NameU="Node{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{w}"/>
      <Cell N="Height" V="{h}"/>
      <Cell N="LocPinX" V="{w/2}"/>
      <Cell N="LocPinY" V="{h/2}"/>
      <Cell N="Angle" V="0"/>
      <Cell N="FlipX" V="0"/>
      <Cell N="FlipY" V="0"/>
      <Cell N="ResizeMode" V="0"/>
      <Section N="Fill">
        <Cell N="FillForegnd" V="{fill}"/>
        <Cell N="FillBkgnd" V="{fill}"/>
        <Cell N="FillPattern" V="1"/>
      </Section>
      <Section N="Line">
        <Cell N="LineColor" V="{border}"/>
        <Cell N="LineWeight" V="0.015"/>
        <Cell N="Rounding" V="0.1"/>
      </Section>
      <Section N="Character">
        <Cell N="Size" V="0.1667"/>
        <Cell N="Color" V="#333333"/>
      </Section>
      <Text>{text}</Text>
    </Shape>'''

    def _graph_connector_xml(self, sid, from_pos, to_pos, label, color):
        x1 = from_pos['x'] + from_pos['w'] / 2
        y1 = from_pos['y'] + from_pos['h'] / 2
        x2 = to_pos['x'] + to_pos['w'] / 2
        y2 = to_pos['y'] + to_pos['h'] / 2

        def clip(px, py, qx, qy, w, h):
            dx = qx - px
            dy = qy - py
            if dx == 0 and dy == 0:
                return px, py
            tx = (w / 2) / abs(dx) if dx != 0 else float('inf')
            ty = (h / 2) / abs(dy) if dy != 0 else float('inf')
            t = min(tx, ty)
            return px + dx * t, py + dy * t

        cx1, cy1 = clip(x1, y1, x2, y2, from_pos['w'], from_pos['h'])
        cx2, cy2 = clip(x2, y2, x1, y1, to_pos['w'], to_pos['h'])

        pin_x = (cx1 + cx2) / 2
        pin_y = (cy1 + cy2) / 2
        w = max(abs(cx2 - cx1), 0.001)
        h = max(abs(cy2 - cy1), 0.001)

        lx1 = cx1 - (pin_x - w / 2)
        ly1 = cy1 - (pin_y - h / 2)
        lx2 = cx2 - (pin_x - w / 2)
        ly2 = cy2 - (pin_y - h / 2)

        line_color = _safe_color(color, '#666666')
        text_xml = f'      <Text>{_xml_escape(label)}</Text>\n' if label else ''

        return f'''<Shape ID="{sid}" NameU="Connector{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{w}"/>
      <Cell N="Height" V="{h}"/>
      <Cell N="LocPinX" V="{w/2}"/>
      <Cell N="LocPinY" V="{h/2}"/>
      <Cell N="Angle" V="0"/>
      <Section N="Geometry" IX="0">
        <Row T="MoveTo" IX="1">
          <Cell N="X" V="{lx1}"/>
          <Cell N="Y" V="{ly1}"/>
        </Row>
        <Row T="LineTo" IX="2">
          <Cell N="X" V="{lx2}"/>
          <Cell N="Y" V="{ly2}"/>
        </Row>
      </Section>
      <Section N="Line">
        <Cell N="LineColor" V="{line_color}"/>
        <Cell N="LineWeight" V="0.015"/>
        <Cell N="EndArrow" V="4"/>
      </Section>
      <Section N="Character">
        <Cell N="Size" V="0.125"/>
        <Cell N="Color" V="{line_color}"/>
      </Section>
{text_xml}    </Shape>'''
