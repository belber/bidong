// 封面地址两种形态都能渲染：生产（COS 绝对地址）原样用，开发（本地相对路径）拼 apiBase。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');
const BASE = 'http://192.168.31.179:8000';

let api;
let resolveMediaUrl;

jest.mock('../miniprogram/utils/api.js', () => {
  const real = jest.requireActual('../miniprogram/utils/api.js');
  return Object.assign({}, real, {
    getCards: () => Promise.resolve((global.__CARDS__ || [])),
    getBinding: () => Promise.resolve({ bound: false }),
    deleteCard: () => Promise.resolve()
  });
});

beforeEach(() => {
  jest.resetModules();
  api = require('../miniprogram/utils/api.js');
  resolveMediaUrl = api.resolveMediaUrl;
});

describe('resolveMediaUrl', () => {
  test('本地相对路径拼上 apiBase', () => {
    const { app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    expect(resolveMediaUrl('/media/covers/a.jpg')).toBe(BASE + '/media/covers/a.jpg');
  });

  test('生产 COS 绝对地址原样返回', () => {
    const { app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    const cos = 'https://bucket.cos.ap-shanghai.myqcloud.com/covers/a.jpg';
    expect(resolveMediaUrl(cos)).toBe(cos);
    expect(resolveMediaUrl('http://old-host:8000/media/covers/a.jpg'))
      .toBe('http://old-host:8000/media/covers/a.jpg');
  });

  test('没有斜杠的相对路径也能拼', () => {
    const { app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    expect(resolveMediaUrl('media/covers/a.jpg')).toBe(BASE + '/media/covers/a.jpg');
  });

  test('apiBase 末尾带斜杠不会拼出双斜杠', () => {
    const { app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE + '/';
    expect(resolveMediaUrl('/media/covers/a.jpg')).toBe(BASE + '/media/covers/a.jpg');
  });

  test('空值原样返回，取不到 apiBase 时退回原值', () => {
    const { app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    expect(resolveMediaUrl('')).toBe('');
    expect(resolveMediaUrl(null)).toBe(null);

    app.globalData.apiBase = '';
    expect(resolveMediaUrl('/media/covers/a.jpg')).toBe('/media/covers/a.jpg');
  });
});

describe('收藏夹卡片封面', () => {
  test('列表加载时把相对路径补成可渲染地址', async () => {
    const { ctx, app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    global.__CARDS__ = [
      {
        id: 1,
        bvid: 'BV1',
        cover_url: '/media/covers/BV1.jpg',
        tags: [],
        month: '2026-10',
        collected_at: 1,
        duration: 61,
        partition: '知识',
        up_name: '某UP',
        source: 'local'
      }
    ];
    ctx.onLoad();

    await new Promise((resolve) => ctx.loadCards(resolve));
    ctx.rebuild(); // 页面上是 setData 回调里触发的，测试环境手动补一次

    expect(ctx.data.cards[0].cover_url).toBe(BASE + '/media/covers/BV1.jpg');
    expect(ctx.data.groups[0].items[0].cover_url).toBe(BASE + '/media/covers/BV1.jpg');
    global.__CARDS__ = [];
  });

  test('生产 COS 地址原样透传（不被 apiBase 改写）', async () => {
    const { ctx, app } = loadPage(COLLECT);
    app.globalData.apiBase = BASE;
    const cos = 'https://bucket.cos.ap-shanghai.myqcloud.com/covers/BV2.jpg';
    global.__CARDS__ = [
      {
        id: 2,
        bvid: 'BV2',
        cover_url: cos,
        tags: [],
        month: '2026-10',
        collected_at: 2,
        duration: 61,
        partition: '知识',
        up_name: '某UP',
        source: 'local'
      }
    ];
    ctx.onLoad();

    await new Promise((resolve) => ctx.loadCards(resolve));

    expect(ctx.data.cards[0].cover_url).toBe(cos);
    global.__CARDS__ = [];
  });
});
