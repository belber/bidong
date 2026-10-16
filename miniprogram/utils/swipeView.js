// 左右滑动切换收藏夹视图：左滑 → 网格，右滑 → 列表。
// 判定故意保守：横向位移要够长、且明显压过纵向，否则信息流里的上下滚动会被抢走。
const { VIEW_LIST, VIEW_GRID } = require('./viewPref.js');

const SWIPE_MIN_DISTANCE = 40; // 逻辑像素，小于这个距离当手指抖动
const SWIPE_AXIS_RATIO = 1.5; // 横向位移要达到纵向的 1.5 倍才算「横向滑动」

function nextViewForSwipe(input) {
  const dx = input && input.dx;
  const dy = input && input.dy;
  const view = input && input.view;
  const min = (input && input.minDistance) || SWIPE_MIN_DISTANCE;
  const ratio = (input && input.axisRatio) || SWIPE_AXIS_RATIO;

  if (!isFinite(dx) || !isFinite(dy)) {
    return null;
  }
  if (Math.abs(dx) < min) {
    return null;
  }
  if (Math.abs(dx) < Math.abs(dy) * ratio) {
    return null;
  }

  const next = dx < 0 ? VIEW_GRID : VIEW_LIST;
  return next === view ? null : next;
}

module.exports = {
  SWIPE_MIN_DISTANCE,
  SWIPE_AXIS_RATIO,
  nextViewForSwipe
};
