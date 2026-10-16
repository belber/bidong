// 左右滑动切换视图：左滑 → 网格，右滑 → 列表。
// 判定要够保守：横向位移要够长，且明显压过纵向，否则会和上下滚动抢手势。
const {
  SWIPE_MIN_DISTANCE,
  SWIPE_AXIS_RATIO,
  nextViewForSwipe
} = require('../miniprogram/utils/swipeView.js');

describe('nextViewForSwipe', () => {
  test('左滑切网格、右滑切列表', () => {
    expect(nextViewForSwipe({ dx: -80, dy: 0, view: 'list' })).toBe('grid');
    expect(nextViewForSwipe({ dx: 80, dy: 0, view: 'grid' })).toBe('list');
  });

  test('位移不够长当抖动，不切换', () => {
    expect(nextViewForSwipe({ dx: -(SWIPE_MIN_DISTANCE - 1), dy: 0, view: 'list' })).toBe(null);
    expect(nextViewForSwipe({ dx: 0, dy: 0, view: 'grid' })).toBe(null);
  });

  test('纵向为主时不切换（滚动优先）', () => {
    expect(nextViewForSwipe({ dx: 60, dy: 60, view: 'grid' })).toBe(null);
    expect(nextViewForSwipe({ dx: -60, dy: 300, view: 'list' })).toBe(null);
    expect(nextViewForSwipe({ dx: 60, dy: 60 / SWIPE_AXIS_RATIO, view: 'grid' })).toBe('list');
  });

  test('已经在目标视图时不切换', () => {
    expect(nextViewForSwipe({ dx: -80, dy: 0, view: 'grid' })).toBe(null);
    expect(nextViewForSwipe({ dx: 80, dy: 0, view: 'list' })).toBe(null);
  });

  test('缺口数据或脏数据不切换', () => {
    expect(nextViewForSwipe({ dx: NaN, dy: 0, view: 'grid' })).toBe(null);
    expect(nextViewForSwipe({ dx: 80, view: 'list' })).toBe(null);
    expect(nextViewForSwipe({})).toBe(null);
  });

  test('阈值可覆盖，方便真机上调手感', () => {
    expect(nextViewForSwipe({ dx: -30, dy: 0, view: 'list', minDistance: 20 })).toBe('grid');
    expect(nextViewForSwipe({ dx: 60, dy: 40, view: 'grid', axisRatio: 2 })).toBe(null);
  });
});
