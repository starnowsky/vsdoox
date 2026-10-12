"""Движок топологии: строит граф L2-связности и вычисляет путь через МЭ.

Работает с «чистыми» структурами (словарями), не зависит от базы данных:
  nodes — список {id, type, name, x, y, attributes, ...}
  links — список {source_id, target_id, ...}

Именно здесь реализовано главное требование: при заданном сетевом
взаимодействии между двумя объектами система сама определяет, через какие
межсетевые экраны проходит путь.
"""
from collections import deque


def build_graph(nodes, links):
    """Строит неориентированный граф смежности.

    Учитывает два типа рёбер:
      - вложенность (parent_id): сервер → сеть → ЦОД, МСЭ → ЦОД;
      - физические линки (links): связи между МСЭ и т.п.

    Возвращает {id: [соседние id, ...]}.
    """
    graph = {}
    ids = {str(n['id']) for n in nodes}
    for n in nodes:
        graph[str(n['id'])] = []

    # Рёбра вложенности
    for n in nodes:
        parent_id = n.get('parent_id')
        if parent_id and str(parent_id) in ids:
            graph[str(n['id'])].append(str(parent_id))
            graph[str(parent_id)].append(str(n['id']))

    # Физические линки
    for link in links:
        s = str(link['source_id'])
        t = str(link['target_id'])
        graph.setdefault(s, []).append(t)
        graph.setdefault(t, []).append(s)
    return graph


def compute_path(graph, source_id, target_id):
    """Кратчайший путь (BFS) от source_id до target_id.

    Возвращает список id [source, ..., target] либо None, если пути нет.
    """
    source_id = str(source_id)
    target_id = str(target_id)
    if source_id not in graph or target_id not in graph:
        return None
    if source_id == target_id:
        return [source_id]

    prev = {source_id: None}
    queue = deque([source_id])
    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, []):
            if neighbor not in prev:
                prev[neighbor] = current
                if neighbor == target_id:
                    path = [target_id]
                    while path[-1] != source_id:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(neighbor)
    return None


def analyze_interaction(nodes, links, source_id, target_id):
    """Анализирует взаимодействие между двумя объектами.

    Возвращает словарь:
      found     — найден ли путь;
      path      — полный путь (id узлов/линков) от source до target;
      firewalls — id межсетевых экранов на пути;
      segments  — id остальных узлов на пути (сети, серверы и т.п.).
    """
    graph = build_graph(nodes, links)
    path = compute_path(graph, source_id, target_id)
    if path is None:
        return {'found': False, 'path': [], 'firewalls': [], 'segments': []}

    type_by_id = {str(n['id']): n.get('type') for n in nodes}
    firewalls = [nid for nid in path if type_by_id.get(nid) == 'firewall']
    segments = [nid for nid in path if type_by_id.get(nid) != 'firewall']
    return {'found': True, 'path': path, 'firewalls': firewalls, 'segments': segments}
