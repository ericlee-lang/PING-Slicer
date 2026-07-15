"use strict";

const assert = require("node:assert/strict");
const { clampSizeMm, fitAspectSize } = require("../resources/web/phototile/size_ratio.js");

{
  const result = fitAspectSize({ width: 100, height: 75, aspect: 493 / 376, changed: "width" });
  assert.deepEqual(result, { width: 100, height: 131.1 });
}

{
  const result = fitAspectSize({ width: 100, height: 132, aspect: 493 / 376, changed: "height" });
  assert.deepEqual(result, { width: 100.7, height: 132 });
}

{
  const result = fitAspectSize({ width: 400, height: 75, aspect: 2, changed: "width" });
  assert.deepEqual(result, { width: 200, height: 400 });
}

{
  const result = fitAspectSize({ width: 100, height: 75, aspect: Number.NaN, changed: "width" });
  assert.deepEqual(result, { width: 100, height: 75 });
  assert.equal(clampSizeMm(999, 100), 400);
}

console.log("photo-tile proportional size tests: PASS");
