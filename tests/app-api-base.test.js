// 审核版/体验版/开发版都必须用备案域名，绝不能把局域网 IP 打进审核包。
const path = require('path');

const APP = path.join(__dirname, '../miniprogram/app.js');

function loadApp({ envVersion, throws = false }) {
  let app = null;
  global.wx = {
    getAccountInfoSync: () => {
      if (throws) throw new Error('boom');
      return { miniProgram: { envVersion } };
    },
    request: () => {}
  };
  global.App = (obj) => { app = obj; };
  global.getApp = () => app;
  jest.resetModules();
  require(APP);
  return app;
}

describe('API 域名', () => {
  test.each(['develop', 'trial', 'release'])('%s 环境都走正式域名', (envVersion) => {
    const app = loadApp({ envVersion });
    expect(app.globalData.apiBase).toBe('https://api.beastnotes.cn');
  });

  test('取不到环境信息时也走正式域名', () => {
    const app = loadApp({ throws: true });
    expect(app.globalData.apiBase).toBe('https://api.beastnotes.cn');
  });

  test('源码里不再有局域网/本机 API 地址', () => {
    const source = require('fs').readFileSync(APP, 'utf8');
    expect(source).not.toMatch(/https?:\/\/(192\.168|10\.|127\.0\.0\.1|localhost)/);
  });
});
