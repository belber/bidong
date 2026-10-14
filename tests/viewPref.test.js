const {
  VIEW_LIST,
  VIEW_GRID,
  DEFAULT_COLS,
  ALLOWED_COLS,
  STORAGE_KEY_VIEW,
  STORAGE_KEY_COLS,
  normalizeView,
  normalizeCols,
  readPrefs,
  savePrefs,
  hasSeenPinchHint,
  markPinchHintSeen,
  STORAGE_KEY_PINCH_HINT
} = require('../miniprogram/utils/viewPref.js');

function fakeStorage(initial) {
  const box = Object.assign({}, initial);
  return {
    box,
    storage: {
      getStorageSync: (key) => box[key],
      setStorageSync: (key, value) => { box[key] = value; }
    }
  };
}

describe('normalizeView', () => {
  test('list / grid 原样返回', () => {
    expect(normalizeView('list')).toBe(VIEW_LIST);
    expect(normalizeView('grid')).toBe(VIEW_GRID);
  });

  test('缺失或非法值回落到网格', () => {
    expect(normalizeView(undefined)).toBe(VIEW_GRID);
    expect(normalizeView('')).toBe(VIEW_GRID);
    expect(normalizeView('cards')).toBe(VIEW_GRID);
  });
});

describe('normalizeCols', () => {
  test('2 / 3 / 4 原样返回', () => {
    ALLOWED_COLS.forEach((n) => expect(normalizeCols(n)).toBe(n));
  });

  test('本地缓存读出的字符串数字也能识别', () => {
    expect(normalizeCols('3')).toBe(3);
    expect(normalizeCols('4')).toBe(4);
  });

  test('越界或非法值回落到默认列数', () => {
    expect(normalizeCols(1)).toBe(DEFAULT_COLS);
    expect(normalizeCols(5)).toBe(DEFAULT_COLS);
    expect(normalizeCols('abc')).toBe(DEFAULT_COLS);
    expect(normalizeCols(undefined)).toBe(DEFAULT_COLS);
    expect(normalizeCols(null)).toBe(DEFAULT_COLS);
  });
});

describe('readPrefs', () => {
  test('空缓存返回默认：网格 + 默认列数', () => {
    const { storage } = fakeStorage({});
    expect(readPrefs(storage)).toEqual({ view: VIEW_GRID, cols: DEFAULT_COLS });
  });

  test('读回已保存的偏好', () => {
    const { storage } = fakeStorage({ [STORAGE_KEY_VIEW]: 'list', [STORAGE_KEY_COLS]: 3 });
    expect(readPrefs(storage)).toEqual({ view: 'list', cols: 3 });
  });

  test('缓存里是脏数据时回落默认', () => {
    const { storage } = fakeStorage({ [STORAGE_KEY_VIEW]: 'whatever', [STORAGE_KEY_COLS]: 9 });
    expect(readPrefs(storage)).toEqual({ view: VIEW_GRID, cols: DEFAULT_COLS });
  });

  test('storage 抛错时不冒泡，退回默认值', () => {
    const storage = {
      getStorageSync: () => { throw new Error('boom'); },
      setStorageSync: () => {}
    };
    expect(readPrefs(storage)).toEqual({ view: VIEW_GRID, cols: DEFAULT_COLS });
  });
});

describe('savePrefs', () => {
  test('写入前做一次归一化', () => {
    const { box, storage } = fakeStorage({});
    savePrefs({ view: 'grid', cols: '4' }, storage);
    expect(box[STORAGE_KEY_VIEW]).toBe('grid');
    expect(box[STORAGE_KEY_COLS]).toBe(4);
  });

  test('未知视图与越界列数都被挡在存储之外', () => {
    const { box, storage } = fakeStorage({});
    savePrefs({ view: 'hacker', cols: 99 }, storage);
    expect(box[STORAGE_KEY_VIEW]).toBe(VIEW_GRID);
    expect(box[STORAGE_KEY_COLS]).toBe(DEFAULT_COLS);
  });

  test('storage 抛错时不冒泡', () => {
    const storage = {
      getStorageSync: () => undefined,
      setStorageSync: () => { throw new Error('quota'); }
    };
    expect(() => savePrefs({ view: 'list', cols: 3 }, storage)).not.toThrow();
  });
});

describe('捏合提示只弹一次', () => {
  test('没提示过 → 需要提示', () => {
    const { storage } = fakeStorage({});
    expect(hasSeenPinchHint(storage)).toBe(false);
  });

  test('标记后 → 不再提示', () => {
    const { box, storage } = fakeStorage({});
    markPinchHintSeen(storage);
    expect(box[STORAGE_KEY_PINCH_HINT]).toBe(1);
    expect(hasSeenPinchHint(storage)).toBe(true);
  });

  test('读缓存出错时按「已提示」处理，避免反复打扰', () => {
    const storage = {
      getStorageSync: () => { throw new Error('boom'); },
      setStorageSync: () => {}
    };
    expect(hasSeenPinchHint(storage)).toBe(true);
  });

  test('标记写失败不冒泡', () => {
    const storage = {
      getStorageSync: () => undefined,
      setStorageSync: () => { throw new Error('quota'); }
    };
    expect(() => markPinchHintSeen(storage)).not.toThrow();
  });
});
