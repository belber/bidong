const {
  MIN_COLS,
  MAX_COLS,
  ZOOM_OUT_SCALE,
  ZOOM_IN_SCALE,
  pinchDistance,
  nextCols,
  createPinchTracker
} = require('../miniprogram/utils/pinchZoom.js');

// 两指水平分开 distance 像素
function pair(distance) {
  const half = distance / 2;
  return [{ clientX: 200 - half, clientY: 300 }, { clientX: 200 + half, clientY: 300 }];
}

describe('pinchDistance', () => {
  test('两指距离按欧氏距离算', () => {
    expect(pinchDistance(pair(200))).toBe(200);
    expect(pinchDistance([{ clientX: 0, clientY: 0 }, { clientX: 3, clientY: 4 }])).toBe(5);
  });

  test('不足两根手指或数据缺失时返回 0', () => {
    expect(pinchDistance([{ clientX: 0, clientY: 0 }])).toBe(0);
    expect(pinchDistance([])).toBe(0);
    expect(pinchDistance(undefined)).toBe(0);
  });
});

describe('nextCols', () => {
  test('捏小到阈值以下：列数 +1', () => {
    expect(nextCols(2, 0.5)).toBe(3);
    expect(nextCols(3, ZOOM_OUT_SCALE)).toBe(4);
  });

  test('放大到阈值以上：列数 -1', () => {
    expect(nextCols(4, 2)).toBe(3);
    expect(nextCols(3, ZOOM_IN_SCALE)).toBe(2);
  });

  test('处在阈值之间不动', () => {
    expect(nextCols(2, 0.81)).toBe(2);
    expect(nextCols(3, 1.24)).toBe(3);
    expect(nextCols(3, 1)).toBe(3);
  });

  test('两端封顶：{} - {} 列', () => {
    expect(nextCols(MIN_COLS, 5)).toBe(MIN_COLS);
    expect(nextCols(MAX_COLS, 0.1)).toBe(MAX_COLS);
  });

  test('脏数据先归一化再算', () => {
    expect(nextCols(9, 0.5)).toBe(MAX_COLS);
    expect(nextCols('2', 0.5)).toBe(3);
    expect(nextCols(undefined, 1.5)).toBe(MIN_COLS);
  });
});

describe('createPinchTracker', () => {
  test('一次手势内每跨一次阈值只改一档，不会连跳', () => {
    const tracker = createPinchTracker(2);
    tracker.begin(200);
    expect(tracker.update(150)).toBe(3); // 0.75 → 3 列，基准重置为 150
    expect(tracker.update(140)).toBe(3); // 0.93 → 不动，避免一路猛跳
    expect(tracker.update(120)).toBe(4); // 0.8 → 4 列
    expect(tracker.update(60)).toBe(4); // 到底不再变
  });

  test('反向捏大能减回列数', () => {
    const tracker = createPinchTracker(4);
    tracker.begin(100);
    expect(tracker.update(150)).toBe(3);
    expect(tracker.update(200)).toBe(2);
    expect(tracker.update(400)).toBe(2); // 已经是 2 列，封顶
  });

  test('基准为 0 / 非法距离时不改变列数、也不产生 NaN', () => {
    const tracker = createPinchTracker(2);
    tracker.begin(0);
    expect(tracker.update(0)).toBe(2);
    expect(tracker.update(100)).toBe(2);
    expect(tracker.update(NaN)).toBe(2);
  });

  test('列数属性随手势更新，供页面渲染', () => {
    const tracker = createPinchTracker(2);
    tracker.begin(200);
    tracker.update(150);
    expect(tracker.cols).toBe(3);
  });
});
