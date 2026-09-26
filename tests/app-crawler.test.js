// 微信搜索爬虫打开页面时会带场景值 1129；小程序把它上报回后端，
// 管理端「搜索爬虫」页才能回答"爬虫到底来没来过"。
const path = require('path');

const APP = path.join(__dirname, '../miniprogram/app.js');

function loadApp() {
  const requests = [];
  let app = null;
  global.wx = {
    getAccountInfoSync: () => ({ miniProgram: { envVersion: 'release' } }),
    request: (opts) => {
      requests.push(opts);
      if (opts.success) opts.success({ statusCode: 200, data: { ok: true } });
    }
  };
  global.App = (obj) => { app = obj; };
  global.getApp = () => app;
  jest.resetModules();
  require(APP);
  return { app, requests };
}

describe('爬虫场景值上报', () => {
  test('场景值 1129 时上报页面路径与参数', () => {
    const { app, requests } = loadApp();
    app.onShow({
      scene: 1129,
      path: 'pages/result/result',
      query: { bvid: 'BV1Nse466EsX' }
    });
    expect(requests).toHaveLength(1);
    expect(requests[0].url).toContain('/api/public/crawler-visit');
    expect(requests[0].data).toEqual({
      path: 'pages/result/result',
      query: 'bvid=BV1Nse466EsX',
      scene: 1129
    });
  });

  test('普通用户打开（别的场景值）不上报', () => {
    const { app, requests } = loadApp();
    app.onShow({ scene: 1001, path: 'pages/home/home' });
    expect(requests).toHaveLength(0);
  });

  test('没有参数也不炸', () => {
    const { app, requests } = loadApp();
    app.onShow({ scene: 1129, path: 'pages/home/home' });
    expect(requests[0].data.query).toBe('');
  });
});
