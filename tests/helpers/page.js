// 小程序页面在 jest 里的最小运行环境：stub 掉 wx / getApp / Page，
// 让测试能真的调用 onLoad / applyResult 这类方法，而不是只做文本断言。

function loadPage(relPath) {
  const toasts = [];
  const titles = [];
  const clipboard = [];
  const stored = {};

  global.wx = {
    showToast: (o) => toasts.push(o.title),
    showLoading: () => {},
    hideLoading: () => {},
    setStorageSync: (k, v) => { stored[k] = v; },
    getStorageSync: (k) => stored[k],
    setClipboardData: (o) => clipboard.push(o.data),
    setNavigationBarTitle: (o) => titles.push(o.title),
    getSystemInfoSync: () => ({ platform: 'devtools' }),
    vibrateShort: () => {}
  };
  const app = { globalData: {} };
  global.getApp = () => app;

  let page = null;
  global.Page = (obj) => { page = obj; };
  jest.resetModules();
  require(relPath);

  const ctx = Object.assign({}, page, {
    data: JSON.parse(JSON.stringify(page.data)),
    setData(patch) { Object.assign(this.data, patch); }
  });
  // 页面里会触发的副作用，测试按需覆写
  ctx.loadMediaSize = () => {};
  ctx.loadUiConfig = () => {};

  return { page, ctx, app, toasts, titles, clipboard, stored };
}

module.exports = { loadPage };
