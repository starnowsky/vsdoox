import io
import math
from vsdx import VisioFile
from lxml import etree

NS = {
    'v': 'http://schemas.microsoft.com/office/visio/2012/main',
}

# Размеры страницы (в дюймах, Visio использует дюймы)
PAGE_W = 11.0
PAGE_H = 8.5

NODE_W = 1.5
NODE_H = 0.75

MARGIN_X = 1.0
MARGIN_Y = 1.0

GRID_COLS_DEFAULT = 4


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

    def _build_shape_xml(self, shape_id, name, x, y, w, h, text):
        """Создаёт XML для одной фигуры (прямоугольник с текстом)."""
        pin_x = x + w / 2
        pin_y = y + h / 2

        shape = etree.SubElement(etree.Element('root'), '{%s}Shape' % NS['v'])
        shape.set('ID', str(shape_id))
        shape.set('NameU', name)
        shape.set('Type', 'Shape')

        # Cell: PinX
        for cell_name, formula in [
            ('PinX', str(pin_x)),
            ('PinY', str(pin_y)),
            ('Width', str(w)),
            ('Height', str(h)),
            ('LocPinX', str(w / 2)),
            ('LocPinY', str(h / 2)),
            ('Angle', '0'),
            ('FlipX', '0'),
            ('FlipY', '0'),
            ('ResizeMode', '0'),
        ]:
            cell = etree.SubElement(shape, '{%s}Cell' % NS['v'])
            cell.set('N', cell_name)
            cell.set('V', formula)

        # Текст
        text_el = etree.SubElement(shape, '{%s}Text' % NS['v'])
        text_el.text = text

        # Секция Fill (заливка)
        section = etree.SubElement(shape, '{%s}Section' % NS['v'])
        section.set('N', 'Fill')
        for n, v in [('FillForegnd', '#DAE8FC'), ('FillBkgnd', '#DAE8FC'),
                     ('FillPattern', '1')]:
            c = etree.SubElement(section, '{%s}Cell' % NS['v'])
            c.set('N', n)
            c.set('V', v)

        # Секция Line (граница)
        section = etree.SubElement(shape, '{%s}Section' % NS['v'])
        section.set('N', 'Line')
        for n, v in [('LineColor', '#6C8EBF'), ('LineWeight', '0.02')]:
            c = etree.SubElement(section, '{%s}Cell' % NS['v'])
            c.set('N', n)
            c.set('V', v)

        return shape

    def _build_connector_xml(self, shape_id, from_pos, to_pos):
        """Простой соединитель: линия от границы одного узла к другому."""
        x1 = from_pos['x'] + from_pos['w'] / 2
        y1 = from_pos['y'] + from_pos['h'] / 2
        x2 = to_pos['x'] + to_pos['w'] / 2
        y2 = to_pos['y'] + to_pos['h'] / 2

        # Обрезаем линию по границе прямоугольника (упрощённо)
        def clip(px, py, qx, qy, w, h):
            dx = qx - px
            dy = qy - py
            if dx == 0 and dy == 0:
                return px, py
            # Ищем пересечение с рамкой
            tx = (w / 2) / abs(dx) if dx != 0 else float('inf')
            ty = (h / 2) / abs(dy) if dy != 0 else float('inf')
            t = min(tx, ty)
            return px + dx * t, py + dy * t

        cx1, cy1 = clip(x1, y1, x2, y2, from_pos['w'], from_pos['h'])
        cx2, cy2 = clip(x2, y2, x1, y1, to_pos['w'], to_pos['h'])

        w = abs(cx2 - cx1)
        h = abs(cy2 - cy1)
        pin_x = (cx1 + cx2) / 2
        pin_y = (cy1 + cy2) / 2

        shape = etree.Element('{%s}Shape' % NS['v'])
        shape.set('ID', str(shape_id))
        shape.set('NameU', f'Connector{shape_id}')
        shape.set('Type', 'Shape')

        for n, v in [
            ('PinX', str(pin_x)),
            ('PinY', str(pin_y)),
            ('Width', str(max(w, 0.01))),
            ('Height', str(max(h, 0.01))),
            ('LocPinX', str(max(w, 0.01) / 2)),
            ('LocPinY', str(max(h, 0.01) / 2)),
            ('Angle', '0'),
        ]:
            c = etree.SubElement(shape, '{%s}Cell' % NS['v'])
            c.set('N', n)
            c.set('V', v)

        # Геометрия — линия
        geom = etree.SubElement(shape, '{%s}Section' % NS['v'])
        geom.set('N', 'Geometry')
        geom.set('IX', '0')

        # Начало
        for n, v, f in [
            ('X', '0', '0'),
            ('Y', str(cy1 - (pin_y - max(h, 0.01) / 2)), None),
        ]:
            pass

        # Упростим: используем MoveTo и LineTo
        move = etree.SubElement(geom, '{%s}Row' % NS['v'])
        move.set('T', 'MoveTo')
        move.set('IX', '1')
        x_cell = etree.SubElement(move, '{%s}Cell' % NS['v'])
        x_cell.set('N', 'X')
        x_cell.set('V', '0')
        y_cell = etree.SubElement(move, '{%s}Cell' % NS['v'])
        y_cell.set('N', 'Y')
        y_cell.set('V', str(cy1 - (pin_y - max(h, 0.01) / 2)))

        line = etree.SubElement(geom, '{%s}Row' % NS['v'])
        line.set('T', 'LineTo')
        line.set('IX', '2')
        x_cell = etree.SubElement(line, '{%s}Cell' % NS['v'])
        x_cell.set('N', 'X')
        x_cell.set('V', str(max(w, 0.01)))
        y_cell = etree.SubElement(line, '{%s}Cell' % NS['v'])
        y_cell.set('N', 'Y')
        y_cell.set('V', str(cy2 - (pin_y - max(h, 0.01) / 2)))

        # Стрелка на конце
        line_sec = etree.SubElement(shape, '{%s}Section' % NS['v'])
        line_sec.set('N', 'Line')
        for n, v in [('EndArrow', '4'), ('LineColor', '#666666'),
                     ('LineWeight', '0.015')]:
            c = etree.SubElement(line_sec, '{%s}Cell' % NS['v'])
            c.set('N', n)
            c.set('V', v)

        return shape

    def build(self, nodes, edges, layout='grid'):
        positions = compute_layout(nodes, edges, layout)

        # Создаём документ с нуля через vsdx — используем пустой файл.
        # vsdx библиотека требует существующий файл. Создадим минимальный
        # VSDX программно (упрощённо — генерируем XML страницы и упаковываем).

        # Более простой путь: создаём минимальный .vsdx вручную (zip).
        import zipfile
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            # [Content_Types].xml
            z.writestr('[Content_Types].xml', self._content_types())

            # _rels/.rels
            z.writestr('_rels/.rels', self._root_rels())

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
</Types>'''

    def _root_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
</Relationships>'''

    def _document_rels(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
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

    def _pages_xml(self):
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xml:space="preserve">
  <Page ID="0" NameU="Page-1" Name="Page-1" ViewScale="1" ViewCenterX="5.5" ViewCenterY="4.25">
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
        text = (node.get('label') or node.get('id') or '').replace('&', '&amp;').replace('<', '&lt;')
        fill = node.get('color', '#DAE8FC')
        border = node.get('border', '#6C8EBF')

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