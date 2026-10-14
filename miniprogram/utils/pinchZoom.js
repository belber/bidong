// 捏合换列数：手感对齐系统相册——捏小 → 列数 +1，撑大 → 列数 -1，实时生效。
// 这里只做纯逻辑（两指距离 → 列数），页面负责把 touch 事件喂进来。

const MIN_COLS = 2;
const MAX_COLS = 4;
const ZOOM_OUT_SCALE = 0.8; // 两指距离缩到这个比例以下 → 加一列
const ZOOM_IN_SCALE = 1.25; // 撑到这个比例以上 → 减一列

function clampCols(value) {
  const cols = parseInt(value, 10);
  if (!isFinite(cols)) {
    return MIN_COLS;
  }
  return Math.min(MAX_COLS, Math.max(MIN_COLS, cols));
}

// 两指当前距离；不足两指或坐标缺失时返回 0（调用方据此判定手势无效）。
function pinchDistance(touches) {
  if (!touches || touches.length < 2) {
    return 0;
  }
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  const distance = Math.sqrt(dx * dx + dy * dy);
  return isFinite(distance) ? distance : 0;
}

// scale = 当前两指距离 / 本次基准距离
function nextCols(cols, scale) {
  const current = clampCols(cols);
  if (!isFinite(scale) || scale <= 0) {
    return current;
  }
  if (scale <= ZOOM_OUT_SCALE) {
    return clampCols(current + 1);
  }
  if (scale >= ZOOM_IN_SCALE) {
    return clampCols(current - 1);
  }
  return current;
}

// 一次手势一个 tracker：每次改档都把基准距离重置成当前距离，
// 所以是「一档一档跟手」，捏得再快也不会一帧从 2 列跳到 4 列。
function createPinchTracker(startCols) {
  let cols = clampCols(startCols);
  let baseline = 0;
  return {
    get cols() {
      return cols;
    },
    begin(distance) {
      baseline = isFinite(distance) && distance > 0 ? distance : 0;
    },
    update(distance) {
      if (!isFinite(distance) || distance <= 0) {
        return cols;
      }
      if (baseline <= 0) {
        // 起手两指几乎重合：先认一个基准，本次不改列数
        baseline = distance;
        return cols;
      }
      const next = nextCols(cols, distance / baseline);
      if (next !== cols) {
        cols = next;
        baseline = distance;
      }
      return cols;
    }
  };
}

module.exports = {
  MIN_COLS,
  MAX_COLS,
  ZOOM_OUT_SCALE,
  ZOOM_IN_SCALE,
  clampCols,
  pinchDistance,
  nextCols,
  createPinchTracker
};
