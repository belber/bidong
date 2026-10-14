// 收藏夹视图偏好：列表 / 网格 + 网格列数。
// 纯前端偏好（不走后端、不入库），存本地缓存，下次进入收藏夹沿用。
// 缓存键与取值收敛在这里，页面只调 readPrefs / savePrefs。

const VIEW_LIST = 'list';
const VIEW_GRID = 'grid';
const DEFAULT_VIEW = VIEW_GRID;
const DEFAULT_COLS = 2;
const ALLOWED_COLS = [2, 3, 4];
const STORAGE_KEY_VIEW = 'collect_view';
const STORAGE_KEY_COLS = 'collect_cols';
const STORAGE_KEY_PINCH_HINT = 'collect_pinch_hint';

// 只有 list 是「例外值」，其余（含 undefined / 脏数据）都回落到网格。
function normalizeView(value) {
  return value === VIEW_LIST ? VIEW_LIST : VIEW_GRID;
}

// 本地缓存读出来可能是字符串，越界值一律回落到默认列数。
function normalizeCols(value) {
  const cols = parseInt(value, 10);
  return ALLOWED_COLS.indexOf(cols) >= 0 ? cols : DEFAULT_COLS;
}

function resolveStorage(storage) {
  if (storage) {
    return storage;
  }
  return typeof wx !== 'undefined' ? wx : null;
}

function readPrefs(storage) {
  const fallback = { view: DEFAULT_VIEW, cols: DEFAULT_COLS };
  const store = resolveStorage(storage);
  if (!store || typeof store.getStorageSync !== 'function') {
    return fallback;
  }
  try {
    return {
      view: normalizeView(store.getStorageSync(STORAGE_KEY_VIEW)),
      cols: normalizeCols(store.getStorageSync(STORAGE_KEY_COLS))
    };
  } catch (err) {
    return fallback;
  }
}

// 写入前先归一化，坏值不落到存储里；写失败不影响本次渲染。
function savePrefs(prefs, storage) {
  const store = resolveStorage(storage);
  if (!store || typeof store.setStorageSync !== 'function') {
    return;
  }
  try {
    store.setStorageSync(STORAGE_KEY_VIEW, normalizeView(prefs && prefs.view));
    store.setStorageSync(STORAGE_KEY_COLS, normalizeCols(prefs && prefs.cols));
  } catch (err) {
    console.warn('[collect] 视图偏好写入失败', err);
  }
}

// 捏合没有任何视觉入口，只能靠一次提示让用户知道；读失败按「已提示」处理，避免反复打扰。
function hasSeenPinchHint(storage) {
  const store = resolveStorage(storage);
  if (!store || typeof store.getStorageSync !== 'function') {
    return true;
  }
  try {
    return !!store.getStorageSync(STORAGE_KEY_PINCH_HINT);
  } catch (err) {
    return true;
  }
}

function markPinchHintSeen(storage) {
  const store = resolveStorage(storage);
  if (!store || typeof store.setStorageSync !== 'function') {
    return;
  }
  try {
    store.setStorageSync(STORAGE_KEY_PINCH_HINT, 1);
  } catch (err) {
    console.warn('[collect] 捏合提示标记写入失败', err);
  }
}

module.exports = {
  VIEW_LIST,
  VIEW_GRID,
  DEFAULT_VIEW,
  DEFAULT_COLS,
  ALLOWED_COLS,
  STORAGE_KEY_VIEW,
  STORAGE_KEY_COLS,
  STORAGE_KEY_PINCH_HINT,
  normalizeView,
  normalizeCols,
  readPrefs,
  savePrefs,
  hasSeenPinchHint,
  markPinchHintSeen
};
