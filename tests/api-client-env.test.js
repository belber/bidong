// 绑定/访问上报要带 envVersion + 实际 API 域名，方便排查审核环境。
const path = require('path');

const API = path.join(__dirname, '../miniprogram/utils/api.js');

function loadApi({ envVersion = 'trial', apiBase = 'https://api.beastnotes.cn', throws = false } = {}) {
  const calls = [];
  global.wx = {
    request: (opts) => {
      calls.push(opts);
      if (opts.success) opts.success({ statusCode: 200, data: { ok: true } });
    },
    getStorageSync: (key) => (key === 'bili_access_token' ? 'test-token' : ''),
    getAccountInfoSync: () => {
      if (throws) throw new Error('unsupported');
      return { miniProgram: { envVersion } };
    }
  };
  global.getApp = () => ({ globalData: { apiBase } });
  jest.resetModules();
  return { api: require(API), calls };
}

describe('客户端环境诊断字段', () => {
  test('访问上报带 env_version / api_base', async () => {
    const { api, calls } = loadApi({ envVersion: 'develop', apiBase: 'http://192.168.31.179:8000' });
    await api.reportVisit('pages/home/home');
    expect(calls[0].data).toMatchObject({
      path: 'pages/home/home',
      env_version: 'develop',
      api_base: 'http://192.168.31.179:8000'
    });
  });

  test('绑定请求同样带上环境信息', async () => {
    const { api, calls } = loadApi({ envVersion: 'trial', apiBase: 'https://api.beastnotes.cn' });
    await api.bind('YVVQKMLKAE');
    expect(calls[0].data).toMatchObject({
      code: 'YVVQKMLKAE',
      env_version: 'trial',
      api_base: 'https://api.beastnotes.cn'
    });
  });

  test('取不到 envVersion 时不报错，字段留空', async () => {
    const { api, calls } = loadApi({ throws: true });
    await api.reportVisit('pages/home/home');
    expect(calls[0].data.env_version).toBe('');
  });
});
