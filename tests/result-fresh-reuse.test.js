// 首页刚解析完就跳结果页：60 秒内直接复用，避免结果页再静默解析一次
// （第二次失败会写错误日志，但页面仍显示第一次的成功结果，容易误判）。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');

const realApi = jest.requireActual('../miniprogram/utils/api.js');
const mockApi = {
  parse: jest.fn(() => Promise.resolve({})),
  getPublicCard: jest.fn(),
  getPublicConfig: jest.fn(() => Promise.resolve({})),
  mediaSize: jest.fn(() => Promise.resolve({})),
  reportDownloadEvent: jest.fn(() => Promise.resolve()),
  resolveMediaUrl: realApi.resolveMediaUrl
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

const CARD = {
  id: 18,
  platform: 'douyin',
  bvid: '7556165407196269882',
  title: '已经解析好的卡片',
  up_name: '作者',
  partition: '',
  pubdate: 0,
  cover_url: '',
  desc: '',
  source_url: '',
  stats: {},
  tags: [],
  media: {},
  subtitles: [],
  features: {}
};

describe('结果页复用刚解析的数据', () => {
  beforeEach(() => {
    mockApi.parse.mockClear();
  });

  test('60 秒内直接复用，不再发第二次 parse', () => {
    const { ctx, app } = loadPage(PAGE);
    app.globalData.pendingResult = CARD;
    app.globalData.pendingAt = Date.now();

    ctx.onLoad({ platform: 'douyin', id: CARD.bvid });

    expect(ctx.data.title).toBe('已经解析好的卡片');
    expect(mockApi.parse).not.toHaveBeenCalled();
  });

  test('超过 60 秒会静默刷新一次', () => {
    const { ctx, app } = loadPage(PAGE);
    app.globalData.pendingResult = CARD;
    app.globalData.pendingAt = Date.now() - 61000;

    ctx.onLoad({ platform: 'douyin', id: CARD.bvid });

    expect(mockApi.parse).toHaveBeenCalledWith(
      'https://www.douyin.com/video/' + CARD.bvid
    );
    expect(ctx.data.loadingVisible).toBe(false); // 静默刷新不弹加载
  });
});
