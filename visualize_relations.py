# visualize_relations.py
#
# This script is used to visualize the relations between entities in the Netbird configuration.
#
# Usage:
# python3 visualize_relations.py
#
# Version: 1.0.1

import os
import yaml
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import argparse

parser = argparse.ArgumentParser(description='Визуализация связей Netbird')
parser.add_argument('--groups', type=str, default=None, help='Список групп через запятую для фильтрации визуализации')
parser.add_argument('--depth', type=int, default=None, help='Глубина связывания от выбранных групп (по умолчанию — без ограничения)')
parser.add_argument('--no-legend', action='store_true', help='Отключить отображение легенды по цветам узлов')
args = parser.parse_args()

if args.groups:
    filter_groups = set([g.strip() for g in args.groups.split(',') if g.strip()])
else:
    filter_groups = None

# Сбор всех сущностей и связей
G = nx.Graph()

# Группы
groups = {}
if os.path.isdir('groups'):
    for fname in os.listdir('groups'):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join('groups', fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for g in configs:
                        if g and 'name' in g:
                            groups[g['name']] = g
                            G.add_node(g['name'], type='group')
                elif isinstance(configs, dict) and 'name' in configs:
                    groups[configs['name']] = configs
                    G.add_node(configs['name'], type='group')

# Пользователи
if os.path.isdir('users'):
    for fname in os.listdir('users'):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join('users', fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for u in configs:
                        if u and 'email' in u:
                            G.add_node(u['email'], type='user')
                            for g in u.get('auto_groups', []):
                                G.add_edge(u['email'], g, label='auto_group')
                elif isinstance(configs, dict) and 'email' in configs:
                    G.add_node(configs['email'], type='user')
                    for g in configs.get('auto_groups', []):
                        G.add_edge(configs['email'], g, label='auto_group')

# Пиры в группах
for g in groups.values():
    for peer in g.get('peers', []):
        G.add_node(peer, type='peer')
        G.add_edge(g['name'], peer, label='peer')

# Ресурсы
if os.path.isdir('resources'):
    for fname in os.listdir('resources'):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            network_name = fname.rsplit('.', 1)[0]
            with open(os.path.join('resources', fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for r in configs:
                        if r and 'name' in r:
                            G.add_node(r['name'], type='resource')
                            for gname in r.get('groups', []):
                                G.add_edge(r['name'], gname, label='resource-group')
                elif isinstance(configs, dict) and 'name' in configs:
                    G.add_node(configs['name'], type='resource')
                    for gname in configs.get('groups', []):
                        G.add_edge(configs['name'], gname, label='resource-group')

# Роуты
if os.path.isdir('routes'):
    for fname in os.listdir('routes'):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join('routes', fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for r in configs:
                        if r and 'name' in r:
                            G.add_node(r['name'], type='route')
                            for gname in r.get('peer_groups', []):
                                G.add_edge(r['name'], gname, label='route-group')
                elif isinstance(configs, dict) and 'name' in configs:
                    G.add_node(configs['name'], type='route')
                    for gname in configs.get('peer_groups', []):
                        G.add_edge(configs['name'], gname, label='route-group')

# Политики
if os.path.isdir('policy'):
    for fname in os.listdir('policy'):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join('policy', fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for p in configs:
                        if p and 'name' in p:
                            G.add_node(p['name'], type='policy')
                            for rule in p.get('rules', []):
                                for gname in rule.get('sources', []):
                                    G.add_edge(p['name'], gname, label='policy-source')
                                for gname in rule.get('destinations', []):
                                    G.add_edge(p['name'], gname, label='policy-dest')
                elif isinstance(configs, dict) and 'name' in configs:
                    G.add_node(configs['name'], type='policy')
                    for rule in configs.get('rules', []):
                        for gname in rule.get('sources', []):
                            G.add_edge(configs['name'], gname, label='policy-source')
                        for gname in rule.get('destinations', []):
                            G.add_edge(configs['name'], gname, label='policy-dest')

# После построения графа G:
if filter_groups:
    nodes_to_keep = set()
    for group in filter_groups:
        if group in G:
            nodes_to_keep.add(group)
            if args.depth is not None:
                # BFS до нужной глубины
                queue = [(group, 0)]
                visited = set([group])
                while queue:
                    node, depth = queue.pop(0)
                    if depth >= args.depth:
                        continue
                    for neighbor in G.neighbors(node):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            nodes_to_keep.add(neighbor)
                            queue.append((neighbor, depth + 1))
            else:
                nodes_to_keep.update(nx.node_connected_component(G, group))
    G = G.subgraph(nodes_to_keep).copy()
    # Пересчитываем позиции только для оставшихся
    pos = nx.spring_layout(G, k=0.5, iterations=100)
    node_colors = []
    for n in G.nodes(data=True):
        t = n[1].get('type')
        if t == 'group':
            node_colors.append('skyblue')
        elif t == 'user':
            node_colors.append('orange')
        elif t == 'peer':
            node_colors.append('green')
        elif t == 'resource':
            node_colors.append('violet')
        elif t == 'route':
            node_colors.append('red')
        elif t == 'policy':
            node_colors.append('yellow')
        else:
            node_colors.append('gray')

# Визуализация
plt.figure(figsize=(18, 12))
pos = nx.spring_layout(G, k=0.5, iterations=100)
node_colors = []
for n in G.nodes(data=True):
    t = n[1].get('type')
    if t == 'group':
        node_colors.append('skyblue')
    elif t == 'user':
        node_colors.append('orange')
    elif t == 'peer':
        node_colors.append('green')
    elif t == 'resource':
        node_colors.append('violet')
    elif t == 'route':
        node_colors.append('red')
    elif t == 'policy':
        node_colors.append('yellow')
    else:
        node_colors.append('gray')

fig, ax = plt.subplots(figsize=(18, 12))

nodes = nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=800)
edges = nx.draw_networkx_edges(G, pos, ax=ax, edge_color='gray')
labels = nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)
plt.title('Netbird: облако связей между сущностями')
plt.tight_layout()

_drag_data = {'node': None, 'offset': (0, 0)}

# Получаем список позиций и обратное соответствие координат -> node
node_positions = {n: pos[n] for n in G.nodes}

def get_node_under_point(event):
    if event.inaxes != ax:
        return None
    xy = np.array([event.xdata, event.ydata])
    min_dist = float('inf')
    closest = None
    for n, p in node_positions.items():
        dist = np.linalg.norm(xy - p)
        if dist < min_dist and dist < 0.07:  # радиус чувствительности
            min_dist = dist
            closest = n
    return closest

def on_press(event):
    node = get_node_under_point(event)
    if node is not None:
        _drag_data['node'] = node
        _drag_data['offset'] = (pos[node][0] - event.xdata, pos[node][1] - event.ydata)

def on_release(event):
    _drag_data['node'] = None

def on_motion(event):
    node = _drag_data['node']
    if node is not None and event.xdata is not None and event.ydata is not None:
        pos[node][0] = event.xdata + _drag_data['offset'][0]
        pos[node][1] = event.ydata + _drag_data['offset'][1]
        node_positions[node] = pos[node]
        ax.clear()
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=800)
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color='gray')
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)
        plt.title('Netbird: облако связей между сущностями')
        plt.tight_layout()
        fig.canvas.draw()

fig.canvas.mpl_connect('button_press_event', on_press)
fig.canvas.mpl_connect('button_release_event', on_release)
fig.canvas.mpl_connect('motion_notify_event', on_motion)

if not args.no_legend:
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='skyblue', edgecolor='k', label='Группы'),
        Patch(facecolor='orange', edgecolor='k', label='Пользователи'),
        Patch(facecolor='green', edgecolor='k', label='Пиры'),
        Patch(facecolor='violet', edgecolor='k', label='Ресурсы'),
        Patch(facecolor='red', edgecolor='k', label='Роуты'),
        Patch(facecolor='yellow', edgecolor='k', label='Политики'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, title='Легенда')

plt.show()
