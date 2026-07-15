(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.PingPhotoTileSize = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function roundMm(value, digits = 1) {
    const scale = 10 ** digits;
    return Math.round(value * scale) / scale;
  }

  function clampSizeMm(value, fallback, min = 20, max = 400) {
    const parsed = Number(value);
    const safe = Number.isFinite(parsed) ? parsed : fallback;
    return Math.max(min, Math.min(max, safe));
  }

  // Keep the source image's height/width ratio while respecting the physical-size limits.
  // If a very long panorama cannot keep both sides above `min`, preserving its ratio wins.
  function fitAspectSize({ width, height, aspect, changed = "width", min = 20, max = 400, digits = 1 }) {
    const ratio = Number(aspect);
    if (!Number.isFinite(ratio) || ratio <= 0) {
      return {
        width: roundMm(clampSizeMm(width, 100, min, max), digits),
        height: roundMm(clampSizeMm(height, 75, min, max), digits)
      };
    }

    let nextWidth;
    let nextHeight;
    if (changed === "height") {
      nextHeight = clampSizeMm(height, 75, min, max);
      nextWidth = nextHeight / ratio;
    } else {
      nextWidth = clampSizeMm(width, 100, min, max);
      nextHeight = nextWidth * ratio;
    }

    const shrink = Math.min(1, max / nextWidth, max / nextHeight);
    nextWidth *= shrink;
    nextHeight *= shrink;

    const grow = Math.max(1, min / nextWidth, min / nextHeight);
    if (nextWidth * grow <= max && nextHeight * grow <= max) {
      nextWidth *= grow;
      nextHeight *= grow;
    }

    return {
      width: roundMm(nextWidth, digits),
      height: roundMm(nextHeight, digits)
    };
  }

  return { clampSizeMm, fitAspectSize, roundMm };
});
