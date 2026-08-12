"""Verify the hand-authored test-case expected outputs using reference solvers.

Covers the ambiguous / multi-output / design problems. Prints any mismatch.
Run from repo root:
    python backend/scripts/verify_coding_test_cases.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coding_test_cases_data import TEST_CASES

ROOT = Path(__file__).resolve().parent.parent.parent


def nums(line: str) -> list[int]:
    return [int(x) for x in line.split()]


def norm(v: Any) -> str:
    return str(v).strip()


# ---------- helpers shared by several solvers ----------

def tree_from_level(line: str):
    if not line.strip():
        return None
    vals = line.split()
    if not vals or vals[0] == "null":
        return None
    nodes = [int(v) if v != "null" else None for v in vals]
    root = {"v": nodes[0], "l": None, "r": None}
    q = deque([root])
    i = 1
    while q and i < len(nodes):
        cur = q.popleft()
        if cur is None:
            continue
        if i < len(nodes):
            v = nodes[i]
            i += 1
            cur["l"] = None if v is None else {"v": v, "l": None, "r": None}
            q.append(cur["l"])
        if i < len(nodes):
            v = nodes[i]
            i += 1
            cur["r"] = None if v is None else {"v": v, "l": None, "r": None}
            q.append(cur["r"])
    return root


def tree_level(root) -> list:
    if root is None:
        return []
    out = []
    q = deque([root])
    while any(q):
        cur = q.popleft()
        if cur is None:
            out.append("null")
            continue
        out.append(str(cur["v"]))
        q.append(cur["l"])
        q.append(cur["r"])
    while out and out[-1] == "null":
        out.pop()
    return out


def list_node(line: str):
    if not line.strip():
        return None
    vals = nums(line)
    head = {"v": vals[0], "n": None}
    cur = head
    for v in vals[1:]:
        cur["n"] = {"v": v, "n": None}
        cur = cur["n"]
    return head


def list_vals(head) -> list:
    out = []
    while head:
        out.append(str(head["v"]))
        head = head["n"]
    return out


# ---------- individual problem solvers ----------

def solve_56(data: list[str]) -> str:
    s, rows = data[0], int(data[1])
    if rows <= 1:
        return s
    lines = [""] * rows
    down = True
    r = 0
    for ch in s:
        lines[r] += ch
        if down:
            if r == rows - 1:
                down, r = False, r - 1
            else:
                r += 1
        else:
            if r == 0:
                down, r = True, 1
            else:
                r -= 1
    return "".join(lines)


def solve_58(data: list[str]) -> str:
    digits = data[0]
    mapping = ["", "", "abc", "def", "ghi", "jkl", "mno", "pqrs", "tuv", "wxyz"]
    res = [""]
    for d in digits:
        res = [p + c for p in res for c in mapping[int(d)]]
    return "\n".join(res)


def solve_62(data: list[str]) -> str:
    cands, target = nums(data[0]), int(data[1])
    res = []

    def rec(i, t, cur):
        if t == 0:
            res.append(tuple(cur))
            return
        if i >= len(cands) or t < 0:
            return
        rec(i, t - cands[i], cur + [cands[i]])
        rec(i + 1, t, cur)

    rec(0, target, [])
    uniq = sorted(set(res))
    return "\n".join(" ".join(map(str, c)) for c in uniq)


def solve_63(data: list[str]) -> str:
    arr = sorted(nums(data[0]))
    res = []

    def rec(cur, left):
        if not left:
            res.append(tuple(cur))
            return
        for i, v in enumerate(left):
            rec(cur + [v], left[:i] + left[i + 1:])

    rec([], arr)
    return "\n".join(" ".join(map(str, c)) for c in res)


def solve_64(data: list[str]) -> str:
    arr = sorted(nums(data[0]))
    res = []

    def rec(i, cur):
        if i == len(arr):
            res.append(tuple(cur))
            return
        rec(i + 1, cur)
        rec(i + 1, cur + [arr[i]])

    rec(0, [])
    res.sort()
    return "\n".join(" ".join(map(str, c)) for c in res)


def solve_72(data: list[str]) -> str:
    target = int(data[-1])
    grid = [nums(line) for line in data[:-1]]
    m, n = len(grid), len(grid[0])
    lo, hi = 0, m * n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        v = grid[mid // n][mid % n]
        if v == target:
            return "true"
        if v < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return "false"


def solve_84(data: list[str]) -> str:
    n = int(data[0])
    adj = [nums(line) for line in data[1:1 + n]]
    return "\n".join(" ".join(map(str, row)) for row in adj)


def solve_86(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    pac = [[False] * n for _ in range(m)]
    atl = [[False] * n for _ in range(m)]

    def dfs(r, c, visited):
        visited[r][c] = True
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n and not visited[nr][nc] and grid[nr][nc] >= grid[r][c]:
                dfs(nr, nc, visited)

    for c in range(n):
        dfs(0, c, pac)
        dfs(m - 1, c, atl)
    for r in range(m):
        dfs(r, 0, pac)
        dfs(r, n - 1, atl)
    res = sorted(
        (r, c) for r in range(m) for c in range(n) if pac[r][c] and atl[r][c]
    )
    return "\n".join(f"{r} {c}" for r, c in res)


def solve_99(data: list[str]) -> str:
    root = tree_from_level(data[0])
    if root is None:
        return ""
    levels = []
    q = deque([root])
    while q:
        row = [x["v"] for x in q]
        levels.append(row)
        nxt = []
        for x in q:
            if x["l"]:
                nxt.append(x["l"])
            if x["r"]:
                nxt.append(x["r"])
        q = deque(nxt)
    out = []
    for i, row in enumerate(levels):
        if i % 2 == 1:
            row = row[::-1]
        out.append(" ".join(map(str, row)))
    return "\n".join(out)


def solve_100(data: list[str]) -> str:
    pre, ino = nums(data[0]), nums(data[1])
    if not pre:
        return ""

    def build(p, i):
        if not p:
            return None
        v = p[0]
        k = i.index(v)
        node = {"v": v, "l": None, "r": None}
        node["l"] = build(p[1:1 + k], i[:k])
        node["r"] = build(p[1 + k:], i[k + 1:])
        return node

    return " ".join(tree_level(build(pre, ino)))


def solve_109(data: list[str]) -> str:
    tokens = data[0].split()
    stack = []
    for t in tokens:
        if t.lstrip("-").isdigit():
            stack.append(int(t))
        else:
            b = stack.pop()
            a = stack.pop()
            if t == "+":
                stack.append(a + b)
            elif t == "-":
                stack.append(a - b)
            elif t == "*":
                stack.append(a * b)
            else:
                stack.append(int(a / b))
    return str(stack[0])


def solve_117(data: list[str]) -> str:
    bars = nums(data[0])
    stack = []
    best = 0
    for i, h in enumerate(bars + [0]):
        while stack and bars[stack[-1]] > h:
            height = bars[stack.pop()]
            width = i if not stack else i - stack[-1] - 1
            best = max(best, height * width)
        stack.append(i)
    return str(best)


def solve_121(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    nxt = [[0] * n for _ in range(m)]
    for r in range(m):
        for c in range(n):
            live = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < m and 0 <= nc < n:
                        live += grid[nr][nc]
            nxt[r][c] = 1 if (grid[r][c] == 1 and live in (2, 3)) or (grid[r][c] == 0 and live == 3) else 0
    return "\n".join(" ".join(map(str, row)) for row in nxt)


def solve_123(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    heights = [0] * n
    best = 0
    for r in range(m):
        for c in range(n):
            heights[c] = heights[c] + 1 if grid[r][c] == 1 else 0
        stack = []
        for i, h in enumerate(heights + [0]):
            while stack and heights[stack[-1]] > h:
                height = heights[stack.pop()]
                width = i if not stack else i - stack[-1] - 1
                best = max(best, height * width)
            stack.append(i)
    return str(best)


def solve_130(data: list[str]) -> str:
    arr = nums(data[0])
    seen = set()
    dups = set()
    for v in arr:
        if v in seen:
            dups.add(v)
        seen.add(v)
    return " ".join(map(str, sorted(dups)))


def solve_132(data: list[str]) -> str:
    s = data[0]
    counter = Counter(s)
    if max(counter.values()) > (len(s) + 1) // 2:
        return ""
    res = []
    while len(res) < len(s):
        nxt = max((ch for ch in counter if not res or ch != res[-1]),
                  key=lambda ch: (counter[ch], ch))
        res.append(nxt)
        counter[nxt] -= 1
    return "".join(res)


def solve_135(data: list[str]) -> str:
    words = set()
    out = []

    def matches(word, pat):
        if len(word) != len(pat):
            return False
        return all(p == "." or p == w for w, p in zip(word, pat, strict=False))

    for line in data:
        parts = line.split()
        if parts[0] == "addWord":
            words.add(parts[1])
        else:
            out.append("true" if any(matches(w, parts[1]) for w in words) else "false")
    return "\n".join(out)


def solve_141(data: list[str]) -> str:
    board = [list(line) for line in data]
    rows, cols, boxes = [set() for _ in range(9)], [set() for _ in range(9)], [set() for _ in range(9)]
    empty = []
    for r in range(9):
        for c in range(9):
            if board[r][c] == ".":
                empty.append((r, c))
            else:
                v = board[r][c]
                rows[r].add(v)
                cols[c].add(v)
                boxes[(r // 3) * 3 + c // 3].add(v)

    def bt(i):
        if i == len(empty):
            return True
        r, c = empty[i]
        b = (r // 3) * 3 + c // 3
        for d in "123456789":
            if d not in rows[r] and d not in cols[c] and d not in boxes[b]:
                rows[r].add(d)
                cols[c].add(d)
                boxes[b].add(d)
                board[r][c] = d
                if bt(i + 1):
                    return True
                rows[r].remove(d)
                cols[c].remove(d)
                boxes[b].remove(d)
                board[r][c] = "."
        return False

    bt(0)
    return "\n".join("".join(row) for row in board)


def solve_142(data: list[str]) -> str:
    n = int(data[0])
    res = []
    board = [["."] * n for _ in range(n)]
    cols, diag1, diag2 = set(), set(), set()

    def bt(r):
        if r == n:
            res.append("\n".join("".join(row) for row in board))
            return
        for c in range(n):
            if c in cols or r - c in diag1 or r + c in diag2:
                continue
            cols.add(c)
            diag1.add(r - c)
            diag2.add(r + c)
            board[r][c] = "Q"
            bt(r + 1)
            board[r][c] = "."
            cols.remove(c)
            diag1.remove(r - c)
            diag2.remove(r + c)

    bt(0)
    return "\n\n".join(res)


def solve_143(data: list[str]) -> str:
    begin, end, words = data[0], data[1], data[2].split()
    if end not in words:
        return "0"
    wset = set(words) | {begin}
    q = deque([(begin, 1)])
    visited = {begin}
    while q:
        w, d = q.popleft()
        for i in range(len(w)):
            for ch in "abcdefghijklmnopqrstuvwxyz":
                nw = w[:i] + ch + w[i + 1:]
                if nw == end:
                    return str(d + 1)
                if nw in wset and nw not in visited:
                    visited.add(nw)
                    q.append((nw, d + 1))
    return "0"


def solve_144(data: list[str]) -> str:
    arr = nums(data[0])
    n = len(arr)
    dp = [[0] * n for _ in range(n)]
    for length in range(1, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            for k in range(i, j + 1):
                left = dp[i][k - 1] if k > i else 0
                right = dp[k + 1][j] if k < j else 0
                lv = arr[i - 1] if i > 0 else 1
                rv = arr[j + 1] if j < n - 1 else 1
                dp[i][j] = max(dp[i][j], left + right + lv * arr[k] * rv)
    return str(dp[0][n - 1])


def solve_146(data: list[str]) -> str:
    snap_id = 0
    history = defaultdict(dict)
    out = []
    for line in data:
        parts = line.split()
        if parts[0] == "set":
            history[int(parts[1])][snap_id] = int(parts[2])
        elif parts[0] == "snap":
            snap_id += 1
        else:
            i, s = int(parts[1]), int(parts[2])
            rec = history[i]
            best = 0
            for k, v in rec.items():
                if k <= s:
                    best = v
            out.append(str(best))
    return "\n".join(out)


def solve_147(data: list[str]) -> str:
    arr = nums(data[0])
    res = []
    for i, v in enumerate(arr):
        res.append(str(sum(1 for x in arr[i + 1:] if x < v)))
    return " ".join(res)


def solve_156(data: list[str]) -> str:
    s, words = data[0], data[1].split()
    wset = set(words)
    memo = {}

    def rec(t):
        if t in memo:
            return memo[t]
        if not t:
            return [""]
        res = []
        for w in wset:
            if t.startswith(w):
                for rest in rec(t[len(w):]):
                    res.append(w + (" " + rest if rest else ""))
        memo[t] = res
        return res

    return "\n".join(sorted(rec(s)))


def solve_157(data: list[str]) -> str:
    arr, k = nums(data[0]), int(data[1])
    count = 0
    for i in range(len(arr)):
        seen = set()
        for j in range(i, len(arr)):
            seen.add(arr[j])
            if len(seen) == k:
                count += 1
            elif len(seen) > k:
                break
    return str(count)


def solve_158(data: list[str]) -> str:
    arr, k = nums(data[0]), int(data[1])
    n = len(arr)
    win = [sum(arr[i:i + k]) for i in range(n - k + 1)]
    left = [0] * len(win)
    best = -1
    for i in range(len(win)):
        if win[i] > best:
            best = win[i]
            left[i] = i
        else:
            left[i] = left[i - 1]
    right = [0] * len(win)
    best = -1
    for i in range(len(win) - 1, -1, -1):
        if win[i] >= best:
            best = win[i]
            right[i] = i
        else:
            right[i] = right[i + 1]
    total, res = -1, []
    for m in range(k, len(win) - k):
        left_index = left[m - k]
        right_index = right[m + k]
        if win[left_index] + win[m] + win[right_index] > total:
            total = win[left_index] + win[m] + win[right_index]
            res = [left_index, m, right_index]
    return " ".join(map(str, res))


def solve_160(data: list[str]) -> str:
    arr = nums(data[0])
    n = len(arr)
    dp = [[0] * n for _ in range(n)]
    for i in range(n - 1, -1, -1):
        for j in range(i, n):
            if i == j:
                dp[i][j] = arr[i]
            else:
                dp[i][j] = max(arr[i] - dp[i + 1][j], arr[j] - dp[i][j - 1])
    return "true" if dp[0][n - 1] >= 0 else "false"


def solve_161(data: list[str]) -> str:
    edge = nums(data[1])
    n = int(data[0])
    seen = [False] * n
    best = -1
    for i in range(n):
        if seen[i]:
            continue
        cur = i
        path = []
        index = {}
        while cur != -1 and not seen[cur]:
            if cur in index:
                best = max(best, len(path) - index[cur])
                break
            index[cur] = len(path)
            path.append(cur)
            cur = edge[cur]
        for v in path:
            seen[v] = True
    return str(best)


def solve_162(data: list[str]) -> str:
    n = int(data[0])
    flights = [nums(line) for line in data[1:-1]]
    src, dst, k = nums(data[-1])
    INF = 10 ** 9
    dist = [INF] * n
    dist[src] = 0
    for _ in range(k + 1):
        nxt = dist[:]
        for u, v, w in flights:
            if dist[u] + w < nxt[v]:
                nxt[v] = dist[u] + w
        dist = nxt
    return str(dist[dst] if dist[dst] < INF else -1)


def solve_163(data: list[str]) -> str:
    n = int(data[0])
    times = [nums(line) for line in data[1:-1]]
    k = int(data[-1])
    g = defaultdict(list)
    for u, v, w in times:
        g[u].append((v, w))
    dist = {i: 10 ** 9 for i in range(1, n + 1)}
    dist[k] = 0
    pq = [(0, k)]
    import heapq
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in g[u]:
            if d + w < dist[v]:
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    mx = max(dist.values())
    return str(mx if mx < 10 ** 9 else -1)


def solve_164(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    import heapq
    pq = [(grid[0][0], 0, 0)]
    seen = [[False] * n for _ in range(m)]
    while pq:
        t, r, c = heapq.heappop(pq)
        if seen[r][c]:
            continue
        seen[r][c] = True
        if r == m - 1 and c == n - 1:
            return str(t)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n and not seen[nr][nc]:
                heapq.heappush(pq, (max(t, grid[nr][nc]), nr, nc))
    return "-1"


def solve_165(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    if grid[0][0] != 0 or grid[m - 1][n - 1] != 0:
        return "-1"
    from collections import deque
    q = deque([(0, 0)])
    seen = {(0, 0)}
    d = 1
    while q:
        for _ in range(len(q)):
            r, c = q.popleft()
            if r == m - 1 and c == n - 1:
                return str(d)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < m and 0 <= nc < n and (nr, nc) not in seen and grid[nr][nc] == 0:
                        seen.add((nr, nc))
                        q.append((nr, nc))
        d += 1
    return "-1"


def solve_166(data: list[str]) -> str:
    begin, end, words = data[0], data[1], data[2].split()
    if end not in words:
        return ""
    wset = set(words)
    if begin not in wset:
        wset.add(begin)
    adj = defaultdict(list)
    for w in wset:
        for i in range(len(w)):
            for ch in "abcdefghijklmnopqrstuvwxyz":
                nw = w[:i] + ch + w[i + 1:]
                if nw in wset and nw != w:
                    adj[w].append(nw)
    dist = {begin: 1}
    q = deque([begin])
    while q:
        w = q.popleft()
        for nb in adj[w]:
            if nb not in dist:
                dist[nb] = dist[w] + 1
                q.append(nb)
    if end not in dist:
        return ""
    paths = []

    def rec(w, path):
        if w == end:
            paths.append(" ".join(path))
            return
        for nb in adj[w]:
            if dist.get(nb) == dist[w] + 1:
                rec(nb, path + [nb])

    rec(begin, [begin])
    return "\n".join(sorted(paths))


def solve_168(data: list[str]) -> str:
    words = data[0].split()
    res = []
    for i in range(len(words)):
        for j in range(len(words)):
            if i != j and (words[i] + words[j]) == (words[i] + words[j])[::-1]:
                res.append((i, j))
    res.sort()
    return "\n".join(f"{i} {j}" for i, j in res)


def solve_169(data: list[str]) -> str:
    num = int(data[0])
    below20 = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
               "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two(n):
        if n < 20:
            return below20[n]
        return (tens[n // 10] + (" " + below20[n % 10] if n % 10 else "")).strip()

    def three(n):
        out = []
        if n // 100:
            out.append(below20[n // 100] + " Hundred")
        rem = n % 100
        if rem:
            out.append(two(rem))
        return " ".join(out)

    if num == 0:
        return "Zero"
    units = ["", " Thousand", " Million", " Billion"]
    parts = []
    i = 0
    while num:
        seg = num % 1000
        if seg:
            parts.append(three(seg) + units[i])
        num //= 1000
        i += 1
    return " ".join(reversed(parts)).strip()


def solve_170(data: list[str]) -> str:
    s = data[0]
    bal = 0
    min_rm = 0
    for ch in s:
        if ch == "(":
            bal += 1
        elif ch == ")":
            if bal:
                bal -= 1
            else:
                min_rm += 1
    min_rm += bal
    res = set()

    def valid(x):
        b = 0
        for ch in x:
            if ch == "(":
                b += 1
            elif ch == ")":
                b -= 1
                if b < 0:
                    return False
        return b == 0

    def rec(i, k, cur):
        if i == len(s):
            if k == 0 and valid(cur):
                res.add("".join(cur))
            return
        rec(i + 1, k, cur + s[i])
        if k > 0 and s[i] in "()":
            rec(i + 1, k - 1, cur)

    rec(0, min_rm, "")
    return "\n".join(sorted(res))


def solve_179(data: list[str]) -> str:
    n1 = int(data[0])
    b1 = [nums(line) for line in data[1:1 + n1]]
    n2 = int(data[1 + n1])
    b2 = [nums(line) for line in data[2 + n1:2 + n1 + n2]]
    dur = int(data[2 + n1 + n2])

    def free(busy):
        f = []
        prev = 0
        for s, e in sorted(busy):
            if prev < s:
                f.append([prev, s])
            prev = max(prev, e)
        f.append([prev, 10 ** 9])
        return f

    f1, f2 = free(b1), free(b2)
    i = j = 0
    while i < len(f1) and j < len(f2):
        lo = max(f1[i][0], f2[j][0])
        hi = min(f1[i][1], f2[j][1])
        if hi - lo >= dur:
            return f"{lo} {lo + dur}"
        if f1[i][1] < f2[j][1]:
            i += 1
        else:
            j += 1
    return ""


def solve_180(data: list[str]) -> str:
    k = int(data[0])
    wages, quality = nums(data[1]), nums(data[2])
    workers = sorted((w / q, q, w) for q, w in zip(quality, wages, strict=False))
    import heapq
    pool = []
    sumq = 0
    best = float("inf")
    for ratio, q, _w in workers:
        heapq.heappush(pool, -q)
        sumq += q
        if len(pool) > k:
            sumq += heapq.heappop(pool)
        if len(pool) == k:
            best = min(best, sumq * ratio)
    return str(round(best))


def solve_181(data: list[str]) -> str:
    a, b, k = nums(data[0]), nums(data[1]), int(data[2])
    import heapq
    heap = [(a[0] + b[0], 0, 0)]
    seen = {(0, 0)}
    out = []
    while heap and len(out) < k:
        _, i, j = heapq.heappop(heap)
        out.append((a[i], b[j]))
        if i + 1 < len(a) and (i + 1, j) not in seen:
            seen.add((i + 1, j))
            heapq.heappush(heap, (a[i + 1] + b[j], i + 1, j))
        if j + 1 < len(b) and (i, j + 1) not in seen:
            seen.add((i, j + 1))
            heapq.heappush(heap, (a[i] + b[j + 1], i, j + 1))
    return "\n".join(f"{x} {y}" for x, y in out)


def solve_182(data: list[str]) -> str:
    grid = [nums(line) for line in data[:-1]]
    k = int(data[-1])
    flat = sorted(x for row in grid for x in row)
    return str(flat[k - 1])


def solve_183(data: list[str]) -> str:
    k = int(data[0])
    lists = [nums(line) for line in data[1:1 + k]]
    import heapq
    heap = [(lst[0], i, 0) for i, lst in enumerate(lists) if lst]
    heapq.heapify(heap)
    mx = max(lst[0] for lst in lists if lst)
    best_lo, best_hi = None, None
    while True:
        lo, i, j = heapq.heappop(heap)
        if best_lo is None or mx - lo < best_hi - best_lo:
            best_lo, best_hi = lo, mx
        if j + 1 >= len(lists[i]):
            break
        nxt = lists[i][j + 1]
        mx = max(mx, nxt)
        heapq.heappush(heap, (nxt, i, j + 1))
    return f"{best_lo} {best_hi}"


def solve_184(data: list[str]) -> str:
    stickers, target = data[0].split(), data[1]
    smap = [Counter(s) for s in stickers]
    memo = {}

    def rec(t):
        if not t:
            return 0
        if t in memo:
            return memo[t]
        tc = Counter(t)
        best = float("inf")
        for s in smap:
            if t[0] not in s:
                continue
            rem = []
            for ch, cnt in tc.items():
                left = cnt - s.get(ch, 0)
                if left > 0:
                    rem.extend(ch * left)
            val = rec("".join(rem))
            if val != float("inf"):
                best = min(best, 1 + val)
        memo[t] = best
        return best

    ans = rec(target)
    return str(ans if ans != float("inf") else -1)


def solve_185(data: list[str]) -> str:
    s = data[0]
    left_index, right_index = 0, len(s) - 1
    count = 0
    left = ""
    right = ""
    while left_index < right_index:
        left += s[left_index]
        right = s[right_index] + right
        if left == right:
            count += 2
            left = right = ""
        left_index += 1
        right_index -= 1
    if left or right or left_index == right_index:
        count += 1
    return str(count)


def solve_187(data: list[str]) -> str:
    arr, k = nums(data[0]), int(data[1])
    n = len(arr)
    flip = [0] * (n + 1)
    cur = 0
    count = 0
    for i in range(n):
        cur ^= flip[i]
        if (arr[i] ^ cur) == 0:
            if i + k > n:
                return "-1"
            count += 1
            cur ^= 1
            flip[i + k] ^= 1
    return str(count)


def solve_188(data: list[str]) -> str:
    n, k = nums(data[0])
    MOD = 10 ** 9 + 7
    dp = [[0] * (k + 1) for _ in range(n + 1)]
    dp[1][1] = 1
    for i in range(2, n + 1):
        for j in range(1, min(i, k) + 1):
            dp[i][j] = (dp[i - 1][j - 1] + (i - 1) * dp[i - 1][j]) % MOD
    return str(dp[n][k])


def solve_189(data: list[str]) -> str:
    n = int(data[0])
    edges = [line.split() for line in data[1:-1]]
    src, dst = int(data[-1].split()[0]), int(data[-1].split()[1])
    g = defaultdict(list)
    for u, v, p in edges:
        u, v, p = int(u), int(v), float(p)
        g[u].append((v, p))
        g[v].append((u, p))
    prob = {i: 0.0 for i in range(n)}
    prob[src] = 1.0
    import heapq
    pq = [(-1.0, src)]
    while pq:
        p, u = heapq.heappop(pq)
        p = -p
        if p < prob[u]:
            continue
        for v, w in g[u]:
            if p * w > prob[v]:
                prob[v] = p * w
                heapq.heappush(pq, (-prob[v], v))
    return f"{prob[dst]:g}"


def solve_190(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    import heapq
    dist = [[10 ** 9] * n for _ in range(m)]
    dist[0][0] = grid[0][0]
    pq = [(grid[0][0], 0, 0)]
    while pq:
        d, r, c = heapq.heappop(pq)
        if d > dist[r][c]:
            continue
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n:
                nd = d + grid[nr][nc]
                if nd < dist[nr][nc]:
                    dist[nr][nc] = nd
                    heapq.heappush(pq, (nd, nr, nc))
    return str(dist[m - 1][n - 1])


def solve_191(data: list[str]) -> str:
    n = int(data[0])
    edges = [nums(line) for line in data[1:]]
    indeg = [0] * (n + 1)
    g = defaultdict(list)
    for a, b in edges:
        g[b].append(a)
        indeg[a] += 1
    q = deque([i for i in range(1, n + 1) if indeg[i] == 0])
    sem = 0
    done = 0
    while q:
        for _ in range(len(q)):
            u = q.popleft()
            done += 1
            for v in g[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        sem += 1
    return str(sem if done == n else -1)


def solve_192(data: list[str]) -> str:
    n, k = nums(data[0])
    prereq = defaultdict(set)
    for line in data[1:]:
        a, b = nums(line)
        prereq[a].add(b)
    need = [0] * n
    for c in range(1, n + 1):
        for p in prereq[c]:
            need[c - 1] |= 1 << (p - 1)
    full = (1 << n) - 1
    memo = {}

    def dp(mask):
        if mask == full:
            return 0
        if mask in memo:
            return memo[mask]
        avail = 0
        for i in range(n):
            if not (mask >> i) & 1 and (need[i] & mask) == need[i]:
                avail |= 1 << i
        best = 10 ** 9
        sub = avail
        while sub:
            if bin(sub).count("1") <= k:
                best = min(best, 1 + dp(mask | sub))
            sub = (sub - 1) & avail
        memo[mask] = best
        return best

    ans = dp(0)
    return str(ans if ans < 10 ** 9 else -1)


def solve_193(data: list[str]) -> str:
    grid = [nums(line) for line in data]
    m, n = len(grid), len(grid[0])
    if grid[0][0] == 1 or grid[m - 1][n - 1] == 1:
        return "0"
    dist = [[10 ** 9] * n for _ in range(m)]
    q = deque()
    for r in range(m):
        for c in range(n):
            if grid[r][c] == 1:
                dist[r][c] = 0
                q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n and dist[nr][nc] > dist[r][c] + 1:
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))
    import heapq
    safety = [[-1] * n for _ in range(m)]
    pq = [(-dist[0][0], 0, 0)]
    while pq:
        neg, r, c = heapq.heappop(pq)
        if safety[r][c] != -1:
            continue
        safety[r][c] = -neg
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n and safety[nr][nc] == -1:
                heapq.heappush(pq, (max(neg, -dist[nr][nc]), nr, nc))
    return str(safety[m - 1][n - 1])


def solve_194(data: list[str]) -> str:
    arr = nums(data[0])
    ops = 0
    for i in range(1, len(arr)):
        if arr[i] < arr[i - 1]:
            ops += arr[i - 1] - arr[i]
            arr[i] = arr[i - 1]
    return str(ops)


def solve_195(data: list[str]) -> str:
    a, b = nums(data[0]), nums(data[1])
    xor_a = 0
    for x in a:
        xor_a ^= x
    xor_b = 0
    for x in b:
        xor_b ^= x
    return str(xor_a & xor_b)


def solve_196(data: list[str]) -> str:
    arr, k = nums(data[0]), int(data[1])
    uniq = list(set(arr))
    cnt = 0
    for i in range(len(uniq)):
        for j in range(i, len(uniq)):
            if bin(uniq[i]).count("1") + bin(uniq[j]).count("1") >= k:
                if i == j:
                    cnt += 1
                else:
                    cnt += 2
    return str(cnt)


def solve_81(data: list[str]) -> str:
    cap = int(data[0])
    vals = {}
    order = deque()
    out = []

    def evict():
        victim = order.popleft()
        del vals[victim]

    for line in data[1:]:
        parts = line.split()
        if parts[0] == "put":
            k, v = int(parts[1]), int(parts[2])
            if k in vals:
                vals[k] = v
                order.remove(k)
                order.append(k)
            else:
                if len(vals) == cap:
                    evict()
                vals[k] = v
                order.append(k)
        else:
            k = int(parts[1])
            if k in vals:
                out.append(str(vals[k]))
                order.remove(k)
                order.append(k)
            else:
                out.append("-1")
    return "\n".join(out)


def solve_172(data: list[str]) -> str:
    cap = int(data[0])
    freq = defaultdict(int)
    order = defaultdict(deque)
    vals = {}
    out = []

    def evict():
        for f in range(1, 10 ** 6):
            q = order[f]
            while q:
                cand = q.popleft()
                if cand in vals and freq[cand] == f:
                    del vals[cand]
                    del freq[cand]
                    return

    for line in data[1:]:
        parts = line.split()
        if parts[0] == "put":
            k, v = int(parts[1]), int(parts[2])
            if k in vals:
                vals[k] = v
                freq[k] += 1
                order[freq[k]].append(k)
            else:
                if len(vals) == cap:
                    evict()
                vals[k] = v
                freq[k] = 1
                order[1].append(k)
        else:
            k = int(parts[1])
            if k in vals:
                out.append(str(vals[k]))
                freq[k] += 1
                order[freq[k]].append(k)
            else:
                out.append("-1")
    return "\n".join(out)


def solve_145(data: list[str]) -> str:
    counts = Counter()
    stack = defaultdict(list)
    maxf = 0
    out = []
    for line in data:
        parts = line.split()
        if parts[0] == "push":
            v = int(parts[1])
            counts[v] += 1
            maxf = max(maxf, counts[v])
            stack[counts[v]].append(v)
        else:
            v = stack[maxf].pop()
            counts[v] -= 1
            if not stack[maxf]:
                maxf -= 1
            out.append(str(v))
    return "\n".join(out)


def solve_134(data: list[str]) -> str:
    root = {"end": 0, "children": {}}
    out = []

    def insert(w):
        node = root
        for ch in w:
            node = node["children"].setdefault(ch, {"end": 0, "children": {}})
        node["end"] += 1

    def count_eq(w):
        node = root
        for ch in w:
            if ch not in node["children"]:
                return 0
            node = node["children"][ch]
        return node["end"]

    def count_pre(p):
        node = root
        for ch in p:
            if ch not in node["children"]:
                return 0
            node = node["children"][ch]
        total = node["end"]
        q = list(node["children"].values())
        while q:
            cur = q.pop()
            total += cur["end"]
            q.extend(cur["children"].values())
        return total

    def erase(w):
        node = root
        for ch in w:
            if ch not in node["children"]:
                return
            node = node["children"][ch]
        node["end"] -= 1

    for line in data:
        parts = line.split()
        op = parts[0]
        if op == "insert":
            insert(parts[1])
        elif op == "erase":
            erase(parts[1])
        elif op == "countWordsEqualTo":
            out.append(str(count_eq(parts[1])))
        else:
            out.append(str(count_pre(parts[1])))
    return "\n".join(out)


def solve_135b(data: list[str]) -> str:
    return solve_135(data)


def solve_175(data: list[str]) -> str:
    r, c = nums(data[0])
    grid = [nums(line) for line in data[1:1 + r]]
    out = []
    for line in data[1 + r:]:
        parts = line.split()
        if parts[0] == "sum":
            r1, c1, r2, c2 = map(int, parts[1:])
            out.append(str(sum(grid[i][j] for i in range(r1, r2 + 1) for j in range(c1, c2 + 1))))
        else:
            rr, cc, v = map(int, parts[1:])
            grid[rr][cc] = v
    return "\n".join(out)


def solve_176(data: list[str]) -> str:
    n = int(data[0])
    tree = [0] * (n + 1)
    out = []

    def add(i, v):
        i += 1
        while i <= n:
            tree[i] += v
            i += i & (-i)

    def prefix(i):
        i += 1
        s = 0
        while i > 0:
            s += tree[i]
            i -= i & (-i)
        return s

    for line in data[1:]:
        parts = line.split()
        if parts[0] == "add":
            add(int(parts[1]), int(parts[2]))
        else:
            out.append(str(prefix(int(parts[1]))))
    return "\n".join(out)


def solve_177(data: list[str]) -> str:
    arr = nums(data[1])
    out = []
    for line in data[2:]:
        parts = line.split()
        if parts[0] == "query":
            left_index, right_index = int(parts[1]), int(parts[2])
            out.append(str(sum(arr[left_index:right_index + 1])))
        else:
            i, v = int(parts[1]), int(parts[2])
            arr[i] = v
    return "\n".join(out)


def solve_124(data: list[str]) -> str:
    nums_l = []
    out = []
    for line in data:
        parts = line.split()
        if parts[0] == "add":
            nums_l.append(int(parts[1]))
        else:
            s = sorted(nums_l)
            n = len(s)
            if n % 2 == 1:
                out.append(str(s[n // 2]))
            else:
                v = (s[n // 2 - 1] + s[n // 2]) / 2
                out.append(f"{v:g}")
    return "\n".join(out)


def solve_132b(data: list[str]) -> str:
    return solve_132(data)


def solve_137(data: list[str]) -> str:
    a, b = nums(data[0]), nums(data[1])
    arr = sorted(a + b)
    n = len(arr)
    if n % 2 == 1:
        return str(arr[n // 2])
    return f"{(arr[n // 2 - 1] + arr[n // 2]) / 2:g}"


SOLVERS = {
    56: solve_56, 58: solve_58, 62: solve_62, 63: solve_63, 64: solve_64,
    72: solve_72, 81: solve_81, 84: solve_84, 86: solve_86, 99: solve_99, 100: solve_100,
    109: solve_109, 117: solve_117, 121: solve_121, 123: solve_123,
    124: solve_124, 130: solve_130, 132: solve_132b, 134: solve_134,
    135: solve_135b, 137: solve_137, 141: solve_141, 142: solve_142,
    143: solve_143, 144: solve_144, 145: solve_145, 146: solve_146,
    147: solve_147, 156: solve_156, 157: solve_157, 158: solve_158,
    160: solve_160, 161: solve_161, 162: solve_162, 163: solve_163,
    164: solve_164, 165: solve_165, 166: solve_166, 168: solve_168,
    169: solve_169, 170: solve_170, 172: solve_172, 175: solve_175,
    176: solve_176, 177: solve_177, 179: solve_179, 180: solve_180,
    181: solve_181, 182: solve_182, 183: solve_183, 184: solve_184,
    185: solve_185, 187: solve_187, 188: solve_188, 189: solve_189,
    190: solve_190, 191: solve_191, 192: solve_192, 193: solve_193,
    194: solve_194, 195: solve_195, 196: solve_196,
}


def main() -> int:
    json.loads((ROOT / "shared" / "coding_questions.json").read_text(encoding="utf-8"))
    mismatches = 0
    for qid, solver in sorted(SOLVERS.items()):
        cases = TEST_CASES.get(qid)
        if not cases:
            print(f"[{qid}] NO TEST CASES")
            mismatches += 1
            continue
        for idx, (inp, expected) in enumerate(cases):
            data = [ln for ln in inp.splitlines()] if inp.strip() else []
            try:
                actual = solver(data)
            except Exception as e:  # noqa: BLE001
                print(f"[{qid}] case {idx}: solver ERROR {e!r}")
                mismatches += 1
                continue
            if norm(actual) != norm(expected):
                print(f"[{qid}] case {idx} MISMATCH")
                print(f"    expected: {expected!r}")
                print(f"    actual  : {actual!r}")
                mismatches += 1
    print(f"\nDone. mismatches={mismatches}")
    return mismatches


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
