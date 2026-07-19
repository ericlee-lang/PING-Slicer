(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module !== "undefined" && module.exports)
    module.exports = api;
  if (root)
    root.PhotoTileMesh = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function cleanIsolated(labels, w, h) {
    const src = new Uint8Array(labels);
    const out = new Uint8Array(src);
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const at = y * w + x;
        const center = src[at];
        const counts = new Map();
        let same = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0)
              continue;
            const value = src[(y + dy) * w + x + dx];
            if (value === center)
              same++;
            counts.set(value, (counts.get(value) || 0) + 1);
          }
        }
        // Only remove a truly isolated pixel. The old 3x3 majority filter ran
        // twice and could cut a printable one-pixel bridge into two islands.
        if (same !== 0)
          continue;
        let best = center;
        let bestCount = 0;
        for (const [value, count] of counts) {
          if (count > bestCount) {
            best = value;
            bestCount = count;
          }
        }
        if (bestCount >= 5)
          out[at] = best;
      }
    }
    return out;
  }

  function smoothLabelNoise(labels, w, h, paletteSize, sx, sz, windowMm, strategy) {
    const src = new Uint8Array(labels);
    const out = new Uint8Array(src);
    const levels = Math.max(1, Math.min(256, Number(paletteSize) || 1));
    const cellX = Number(sx);
    const cellZ = Number(sz);
    const windowSize = Number(windowMm);
    const mode = strategy === "mode" ? "mode" : "median";
    const disabled = !w || !h || src.length !== w * h || windowSize <= 0 ||
      !Number.isFinite(windowSize) || !Number.isFinite(cellX) || cellX <= 0 ||
      !Number.isFinite(cellZ) || cellZ <= 0;
    if (disabled) {
      return {
        labels: out,
        changedPixels: 0,
        changedAreaMm2: 0,
        radiusX: 0,
        radiusY: 0,
        strategy: mode
      };
    }

    // The entered size is the full physical smoothing window, not its radius.
    // A 10 mm setting therefore examines roughly 10 x 10 mm around each cell.
    const radiusX = Math.min(w - 1, Math.max(0, Math.floor(windowSize / (2 * cellX))));
    const radiusY = Math.min(h - 1, Math.max(0, Math.floor(windowSize / (2 * cellZ))));
    if (!radiusX && !radiusY) {
      return {
        labels: out,
        changedPixels: 0,
        changedAreaMm2: 0,
        radiusX,
        radiusY,
        strategy: mode
      };
    }

    // Sliding categorical histogram: memory is O(width * palette), rather
    // than allocating one full integral image for every grayscale level.
    const columnCounts = new Uint32Array(w * levels);
    function addRow(y, delta) {
      if (y < 0 || y >= h)
        return;
      const row = y * w;
      for (let x = 0; x < w; x++) {
        const label = src[row + x];
        if (label < levels)
          columnCounts[x * levels + label] += delta;
      }
    }
    for (let y = 0; y <= Math.min(h - 1, radiusY); y++)
      addRow(y, 1);

    const histogram = new Uint32Array(levels);
    function addColumn(x, delta) {
      if (x < 0 || x >= w)
        return;
      const base = x * levels;
      for (let k = 0; k < levels; k++)
        histogram[k] += delta * columnCounts[base + k];
    }

    let changedPixels = 0;
    for (let y = 0; y < h; y++) {
      if (y > 0) {
        addRow(y - radiusY - 1, -1);
        addRow(y + radiusY, 1);
      }
      histogram.fill(0);
      for (let x = 0; x <= Math.min(w - 1, radiusX); x++)
        addColumn(x, 1);

      const rowTop = Math.max(0, y - radiusY);
      const rowBottom = Math.min(h - 1, y + radiusY);
      const rowCount = rowBottom - rowTop + 1;
      for (let x = 0; x < w; x++) {
        if (x > 0) {
          addColumn(x - radiusX - 1, -1);
          addColumn(x + radiusX, 1);
        }
        const at = y * w + x;
        const center = src[at] < levels ? src[at] : 0;
        let selected = center;
        if (mode === "mode") {
          let bestCount = histogram[center];
          for (let k = 0; k < levels; k++) {
            const count = histogram[k];
            const betterCount = count > bestCount;
            const closerTone = count === bestCount && Math.abs(k - center) < Math.abs(selected - center);
            if (betterCount || closerTone) {
              selected = k;
              bestCount = count;
            }
          }
        } else {
          const colLeft = Math.max(0, x - radiusX);
          const colRight = Math.min(w - 1, x + radiusX);
          const target = Math.floor(((colRight - colLeft + 1) * rowCount) / 2) + 1;
          let cumulative = 0;
          for (let k = 0; k < levels; k++) {
            cumulative += histogram[k];
            if (cumulative >= target) {
              selected = k;
              break;
            }
          }
        }
        out[at] = selected;
        if (selected !== src[at])
          changedPixels++;
      }
    }

    return {
      labels: out,
      changedPixels,
      changedAreaMm2: changedPixels * cellX * cellZ,
      radiusX,
      radiusY,
      strategy: mode
    };
  }

  function filterSmallComponents(labels, w, h, sx, sz, maxSizeMm, options) {
    const original = new Uint8Array(labels);
    let out = new Uint8Array(original);
    const threshold = Number(maxSizeMm);
    const cellX = Number(sx);
    const cellZ = Number(sz);
    const maxPasses = Math.max(1, Math.min(8, Number(options && options.maxPasses) || 4));
    const disabled = !Number.isFinite(threshold) || threshold <= 0 ||
      !Number.isFinite(cellX) || cellX <= 0 || !Number.isFinite(cellZ) || cellZ <= 0;

    if (!w || !h || original.length !== w * h || disabled) {
      return {
        labels: out,
        removedComponents: 0,
        changedPixels: 0,
        changedAreaMm2: 0,
        passes: 0,
        thresholdMm: Math.max(0, Number.isFinite(threshold) ? threshold : 0)
      };
    }

    let removedComponents = 0;
    let changedPasses = 0;
    const n = w * h;

    for (let pass = 0; pass < maxPasses; pass++) {
      const parent = new Int32Array(n);
      const rank = new Uint8Array(n);
      for (let i = 0; i < n; i++)
        parent[i] = i;

      function find(value) {
        let root = value;
        while (parent[root] !== root)
          root = parent[root];
        while (parent[value] !== value) {
          const next = parent[value];
          parent[value] = root;
          value = next;
        }
        return root;
      }
      function unite(a, b) {
        let ra = find(a);
        let rb = find(b);
        if (ra === rb)
          return;
        if (rank[ra] < rank[rb])
          [ra, rb] = [rb, ra];
        parent[rb] = ra;
        if (rank[ra] === rank[rb])
          rank[ra]++;
      }

      // Use four-neighbour components so a diagonal touch remains two islands,
      // exactly like the later mesh/export connectivity analysis.
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const at = y * w + x;
          if (x > 0 && out[at - 1] === out[at])
            unite(at, at - 1);
          if (y > 0 && out[at - w] === out[at])
            unite(at, at - w);
        }
      }
      for (let i = 0; i < n; i++)
        parent[i] = find(i);

      const counts = new Uint32Array(n);
      // GRID_MAX is 3200 — still well within 16-bit coordinates, which save substantial memory here.
      const minX = new Uint16Array(n);
      const maxX = new Uint16Array(n);
      const minY = new Uint16Array(n);
      const maxY = new Uint16Array(n);
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const root = parent[y * w + x];
          if (counts[root] === 0) {
            minX[root] = maxX[root] = x;
            minY[root] = maxY[root] = y;
          } else {
            if (x < minX[root]) minX[root] = x;
            if (x > maxX[root]) maxX[root] = x;
            if (y < minY[root]) minY[root] = y;
            if (y > maxY[root]) maxY[root] = y;
          }
          counts[root]++;
        }
      }

      const small = new Uint8Array(n);
      const epsilon = 1e-9;
      for (let i = 0; i < n; i++) {
        if (!counts[i])
          continue;
        const widthMm = (maxX[i] - minX[i] + 1) * cellX;
        const heightMm = (maxY[i] - minY[i] + 1) * cellZ;
        if (Math.max(widthMm, heightMm) <= threshold + epsilon)
          small[i] = 1;
      }

      // For each small island, count how much boundary it shares with each
      // adjacent major tone. A single numeric-key map avoids allocating one
      // nested Map per speck on noisy, high-resolution photographs.
      // Only major (over-threshold) neighbours are eligible, which prevents
      // small islands from swapping labels in cycles.
      const boundaryCounts = new Map();
      function addBoundary(smallRoot, majorRoot) {
        const key = smallRoot * 256 + out[majorRoot];
        boundaryCounts.set(key, (boundaryCounts.get(key) || 0) + 1);
      }
      function inspectBoundary(a, b) {
        const ra = parent[a];
        const rb = parent[b];
        if (ra === rb)
          return;
        if (small[ra] && !small[rb])
          addBoundary(ra, rb);
        if (small[rb] && !small[ra])
          addBoundary(rb, ra);
      }
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const at = y * w + x;
          if (x + 1 < w)
            inspectBoundary(at, at + 1);
          if (y + 1 < h)
            inspectBoundary(at, at + w);
        }
      }

      const noLabel = 256;
      const bestLabels = new Uint16Array(n);
      bestLabels.fill(noLabel);
      const bestBoundaries = new Uint32Array(n);
      for (const [key, boundary] of boundaryCounts) {
        const smallRoot = Math.floor(key / 256);
        const label = key - smallRoot * 256;
        const previous = bestLabels[smallRoot];
        const betterBoundary = boundary > bestBoundaries[smallRoot];
        const currentDelta = previous === noLabel ? Infinity : Math.abs(out[smallRoot] - previous);
        const nextDelta = Math.abs(out[smallRoot] - label);
        const betterTone = boundary === bestBoundaries[smallRoot] && nextDelta < currentDelta;
        const stableTie = boundary === bestBoundaries[smallRoot] && nextDelta === currentDelta && label < previous;
        if (previous === noLabel || betterBoundary || betterTone || stableTie) {
          bestLabels[smallRoot] = label;
          bestBoundaries[smallRoot] = boundary;
        }
      }

      let replacementCount = 0;
      for (let i = 0; i < n; i++) {
        if (counts[i] && bestLabels[i] !== noLabel)
          replacementCount++;
      }
      if (!replacementCount)
        break;
      const next = new Uint8Array(out);
      for (let i = 0; i < n; i++) {
        const replacement = bestLabels[parent[i]];
        if (replacement !== noLabel)
          next[i] = replacement;
      }
      out = next;
      removedComponents += replacementCount;
      changedPasses++;
    }

    let changedPixels = 0;
    for (let i = 0; i < n; i++) {
      if (out[i] !== original[i])
        changedPixels++;
    }
    return {
      labels: out,
      removedComponents,
      changedPixels,
      changedAreaMm2: changedPixels * cellX * cellZ,
      passes: changedPasses,
      thresholdMm: threshold
    };
  }

  function collectParts(labels, w, h, paletteSize) {
    const n = w * h;
    const parent = new Int32Array(n);
    for (let i = 0; i < n; i++)
      parent[i] = i;

    function find(value) {
      let root = value;
      while (parent[root] !== root)
        root = parent[root];
      while (parent[value] !== value) {
        const next = parent[value];
        parent[value] = root;
        value = next;
      }
      return root;
    }

    function unite(a, b) {
      const ra = find(a);
      const rb = find(b);
      if (ra !== rb)
        parent[rb] = ra;
    }

    // Four-neighbour connectivity is intentional: diagonal pixels that touch at
    // only one point must remain separate watertight shells.
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const at = y * w + x;
        if (x > 0 && labels[at - 1] === labels[at])
          unite(at, at - 1);
        if (y > 0 && labels[at - w] === labels[at])
          unite(at, at - w);
      }
    }
    for (let i = 0; i < n; i++)
      parent[i] = find(i);

    const runsByLabel = Array.from({ length: paletteSize }, () => []);
    const rootsByLabel = Array.from({ length: paletteSize }, () => new Set());
    let totalRuns = 0;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w;) {
        const at = y * w + x;
        const k = labels[at];
        const component = parent[at];
        let x1 = x + 1;
        while (x1 < w && labels[y * w + x1] === k)
          x1++;
        if (k < paletteSize) {
          runsByLabel[k].push([y, x, x1, component]);
          rootsByLabel[k].add(component);
          totalRuns++;
        }
        x = x1;
      }
    }

    const parts = [];
    let components = 0;
    for (let k = 0; k < paletteSize; k++) {
      if (!runsByLabel[k].length)
        continue;
      parts.push({ k, runs: runsByLabel[k], components: rootsByLabel[k].size });
      components += rootsByLabel[k].size;
    }
    return { parts, totalRuns, components };
  }

  function buildLabelMesh(labels, w, h, k, runs, sx, sz, thickness) {
    const vertices = [];
    const triangles = [];
    const vertexIds = new Map();
    const componentIds = new Set();
    let tiles = 0;

    const round3 = value => Math.round(value * 1000) / 1000;
    function sectorAtVertex(gx, gz, cellX, cellY) {
      if (!Number.isInteger(gx) || !Number.isInteger(gz))
        return "";
      const boundaryY = h - gz;
      const has = (x, y) => x >= 0 && x < w && y >= 0 && y < h && labels[y * w + x] === k;
      const mask =
        (has(gx - 1, boundaryY - 1) ? 1 : 0) |
        (has(gx, boundaryY - 1) ? 2 : 0) |
        (has(gx - 1, boundaryY) ? 4 : 0) |
        (has(gx, boundaryY) ? 8 : 0);
      if (mask !== 6 && mask !== 9)
        return "";
      const north = cellY < boundaryY;
      const west = cellX < gx;
      const quadrant = north ? (west ? 1 : 2) : (west ? 4 : 8);
      return `|q${quadrant}`;
    }
    function vertex(component, gx, side, gz, cellX, cellY) {
      // A checkerboard corner may contain the same label in two diagonal
      // quadrants. Give those sectors distinct vertices so the extruded shells
      // do not touch along a four-face, non-manifold depth edge.
      const key = `${component}|${gx}|${side}|${gz}${sectorAtVertex(gx,gz,cellX,cellY)}`;
      let id = vertexIds.get(key);
      if (id !== undefined)
        return id;
      id = vertices.length;
      vertexIds.set(key, id);
      vertices.push([round3(gx * sx), side ? thickness : 0, round3(gz * sz)]);
      return id;
    }
    function quad(a, b, c, d) {
      triangles.push([a, b, c], [a, c, d]);
    }

    function neighbourCuts(neighbourY, x0, x1) {
      const cuts = [x0];
      if (neighbourY >= 0 && neighbourY < h) {
        const base = neighbourY * w;
        for (let x = x0 + 1; x < x1; x++) {
          if (labels[base + x - 1] !== labels[base + x])
            cuts.push(x);
        }
      }
      cuts.push(x1);
      return cuts;
    }

    for (const [y, x0, x1, component] of runs) {
      componentIds.add(component);
      const z0 = h - y - 1;
      const z1 = h - y;
      const v = (gx, side, gz) => {
        const cellX = Math.max(x0, Math.min(x1 - 1, Math.floor(gx)));
        return vertex(component, gx, side, gz, cellX, y);
      };
      const bottomCuts = neighbourCuts(y + 1, x0, x1);
      const topCuts = neighbourCuts(y - 1, x0, x1);
      const boundary = [];
      for (const x of bottomCuts)
        boundary.push([x, z0]);
      for (let i = topCuts.length - 1; i >= 0; i--)
        boundary.push([topCuts[i], z1]);

      // Each scanline run is a rectangle, but its top and bottom can have
      // different split points. A centre fan preserves every shared boundary
      // vertex without propagating cuts through the whole component.
      const cx = (x0 + x1) / 2;
      const cz = (z0 + z1) / 2;
      const frontCenter = v(cx, 0, cz);
      const backCenter = v(cx, 1, cz);
      for (let i = 0; i < boundary.length; i++) {
        const p = boundary[i];
        const q = boundary[(i + 1) % boundary.length];
        triangles.push([
          frontCenter,
          v(p[0], 0, p[1]),
          v(q[0], 0, q[1])
        ]);
        triangles.push([
          backCenter,
          v(q[0], 1, q[1]),
          v(p[0], 1, p[1])
        ]);
      }
      tiles++;

      quad(
        v(x0, 0, z0),
        v(x0, 0, z1),
        v(x0, 1, z1),
        v(x0, 1, z0)
      );
      quad(
        v(x1, 0, z0),
        v(x1, 1, z0),
        v(x1, 1, z1),
        v(x1, 0, z1)
      );

      for (let i = 0; i + 1 < bottomCuts.length; i++) {
        const xa = bottomCuts[i];
        const xb = bottomCuts[i + 1];
        if (y + 1 < h && labels[(y + 1) * w + xa] === k)
          continue;
        quad(
          v(xa, 0, z0),
          v(xa, 1, z0),
          v(xb, 1, z0),
          v(xb, 0, z0)
        );
      }
      for (let i = 0; i + 1 < topCuts.length; i++) {
        const xa = topCuts[i];
        const xb = topCuts[i + 1];
        if (y > 0 && labels[(y - 1) * w + xa] === k)
          continue;
        quad(
          v(xa, 0, z1),
          v(xb, 0, z1),
          v(xb, 1, z1),
          v(xa, 1, z1)
        );
      }
    }

    return {
      vertices,
      triangles,
      tiles,
      components: componentIds.size
    };
  }

  function auditMesh(mesh) {
    const edgeCounts = new Map();
    const parent = new Int32Array(mesh.vertices.length);
    for (let i = 0; i < parent.length; i++)
      parent[i] = i;
    function find(value) {
      while (parent[value] !== value) {
        parent[value] = parent[parent[value]];
        value = parent[value];
      }
      return value;
    }
    function unite(a, b) {
      const ra = find(a);
      const rb = find(b);
      if (ra !== rb)
        parent[rb] = ra;
    }
    function edge(a, b) {
      if (a > b)
        [a, b] = [b, a];
      const key = `${a}|${b}`;
      edgeCounts.set(key, (edgeCounts.get(key) || 0) + 1);
    }

    let signedVolume = 0;
    for (const [a, b, c] of mesh.triangles) {
      edge(a, b);
      edge(b, c);
      edge(c, a);
      unite(a, b);
      unite(b, c);
      const A = mesh.vertices[a];
      const B = mesh.vertices[b];
      const C = mesh.vertices[c];
      signedVolume += (
        A[0] * (B[1] * C[2] - B[2] * C[1]) -
        A[1] * (B[0] * C[2] - B[2] * C[0]) +
        A[2] * (B[0] * C[1] - B[1] * C[0])
      ) / 6;
    }

    let boundaryEdges = 0;
    let nonManifoldEdges = 0;
    for (const count of edgeCounts.values()) {
      if (count === 1)
        boundaryEdges++;
      else if (count !== 2)
        nonManifoldEdges++;
    }
    const roots = new Set();
    for (let i = 0; i < parent.length; i++)
      roots.add(find(i));
    return {
      vertices: mesh.vertices.length,
      triangles: mesh.triangles.length,
      boundaryEdges,
      nonManifoldEdges,
      components: roots.size,
      signedVolume
    };
  }

  // 水平最小可印寬（Eric 2026-07-19 定，縫隙根因）：零件的水平剖面窄於噴頭「進得去、
  // 繞得出來」的寬度（≈2×口徑）就印不出來＝白縫。垂直方向靠層高離散、不受此限，
  // 所以這裡只逐列處理水平向：短於 minCells 的水平連續段併入左右較寬的鄰段。
  // 連結串列合併、合併後回頭重驗，O(n) 攤還；同標籤相鄰段自動收斂。
  function enforceMinHorizontalWidth(labels, w, h, minCells) {
    const out = new Uint8Array(labels);
    let changed = 0, mergedRuns = 0;
    if (!(minCells > 1)) return { labels: out, changedPixels: 0, mergedRuns: 0 };
    const start = new Int32Array(w), len = new Int32Array(w), lab = new Int32Array(w);
    const prev = new Int32Array(w), next = new Int32Array(w);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      let n = 0;
      for (let x = 0; x < w;) {
        const v = out[row + x];
        let x2 = x + 1;
        while (x2 < w && out[row + x2] === v) x2++;
        start[n] = x; len[n] = x2 - x; lab[n] = v;
        prev[n] = n - 1; next[n] = (x2 < w) ? n + 1 : -1;
        n++; x = x2;
      }
      if (n <= 1) continue;
      let head = 0, i = 0;
      while (i !== -1) {
        const p = prev[i], q = next[i];
        if (len[i] >= minCells || (p === -1 && q === -1)) { i = q; continue; }
        const pl = (p === -1) ? -1 : len[p];
        const ql = (q === -1) ? -1 : len[q];
        mergedRuns++;
        if (pl >= ql) {                       // 併入左段（含只剩左段）
          len[p] += len[i];
          next[p] = q; if (q !== -1) prev[q] = p;
          if (q !== -1 && lab[q] === lab[p]) { // 左右同標籤 → 一起收斂
            len[p] += len[q];
            next[p] = next[q]; if (next[q] !== -1) prev[next[q]] = p;
          }
          i = p;                               // 回頭重驗合併後的段
        } else {                               // 併入右段
          start[q] = start[i]; len[q] += len[i];
          prev[q] = p; if (p !== -1) next[p] = q;
          if (p !== -1 && lab[p] === lab[q]) {
            start[q] = start[p]; len[q] += len[p];
            prev[q] = prev[p]; if (prev[p] !== -1) next[prev[p]] = q;
          }
          if (prev[q] === -1) head = q;        // 頭段被併走 → 新頭
          i = (prev[q] !== -1) ? prev[q] : q;
        }
      }
      // 依存活串列重寫該列
      for (let r = head; r !== -1; r = next[r]) {
        const v = lab[r], x0 = start[r], x1 = start[r] + len[r];
        for (let x = x0; x < x1; x++)
          if (out[row + x] !== v) { out[row + x] = v; changed++; }
      }
    }
    return { labels: out, changedPixels: changed, mergedRuns };
  }

  return { cleanIsolated, smoothLabelNoise, filterSmallComponents, collectParts, buildLabelMesh, auditMesh, enforceMinHorizontalWidth };
});
