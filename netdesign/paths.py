"""Trace a physical path through panels, trunks and splices."""

import heapq
from collections import defaultdict, deque


def build_graph(links):
    """links: list of (node_a, node_b, loss_db). Connections work in both directions."""
    graph = defaultdict(dict)
    for a, b, loss in links:
        graph[a][b] = loss
        graph[b][a] = loss
    return graph


def fewest_hops(graph, start, end):
    """Breadth-first search: the path with the fewest hops, or None."""
    prev = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == end:
            return _rebuild(prev, end)
        for nxt in sorted(graph[node]):
            if nxt not in prev:
                prev[nxt] = node
                queue.append(nxt)
    return None


def lowest_loss(graph, start, end):
    """Dijkstra: the path with the lowest total insertion loss. Returns (path, loss_db) or (None, None)."""
    best = {start: 0.0}
    prev = {start: None}
    heap = [(0.0, start)]
    while heap:
        loss, node = heapq.heappop(heap)
        if node == end:
            return _rebuild(prev, end), round(loss, 2)
        if loss > best[node]:
            continue
        for nxt, hop_loss in graph[node].items():
            new_loss = loss + hop_loss
            if new_loss < best.get(nxt, float("inf")):
                best[nxt] = new_loss
                prev[nxt] = node
                heapq.heappush(heap, (new_loss, nxt))
    return None, None


def _rebuild(prev, end):
    path, node = [], end
    while node is not None:
        path.append(node)
        node = prev[node]
    return path[::-1]
