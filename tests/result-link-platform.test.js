// 抖音卡片不能在跳转/分享时退化成 B站 链接：
// ?bvid=<aweme_id> 会让结果页按 B站 拼出 bilibili.com/video/<抖音id>，后端只能猜着解析。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');
const RESULT = path.join(__dirname, '../miniprogram/pages/result/result.js');
const AWEME = '7698027358250432602';

const realApi = jest.requireActual('../miniprogram/utils/api.js');
const mockApi = {
  parse: jest.fn(() => Promise.resolve({ id: 1, bvid: AWEME, platform: 'douyin', media: {} })),
  getPublicCard: jest.fn(),
  getPublicConfig: jest.fn(() => Promise.resolve({})),
  mediaSize: jest.fn(() => Promise.resolve({})),
  reportDownloadEvent: jest.fn(() => Promise.resolve()),
  resolveMediaUrl: realApi.resolveMediaUrl
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

describe('抖音卡片的跳转与分享', () => {
  beforeEach(() => {
    mockApi.parse.mockClear();
  });

  test('收藏夹点抖音卡片时带 platform=douyin', () => {
    const { ctx } = loadPage(COLLECT);
    const nav = [];
    global.wx.navigateTo = (opts) => nav.push(opts.url);
    ctx.setData({
      editing: false,
      cards: [{ id: 7, bvid: AWEME, platform: 'douyin' }]
    });

    ctx.onCardTap({ currentTarget: { dataset: { id: 7 } } });

    expect(nav[0]).toBe('/pages/result/result?platform=douyin&id=' + AWEME);
  });

  test('朋友圈分享抖音卡片时 query 带 platform=douyin', () => {
    const { ctx } = loadPage(RESULT);
    ctx.setData({ isDouyin: true, bvid: AWEME, title: '图文', coverUrl: '' });

    const share = ctx.onShareTimeline();

    expect(share.query).toBe('platform=douyin&id=' + AWEME);
  });

  test('只带 id= 不带 platform 的老链接也能识别成抖音', async () => {
    const { ctx } = loadPage(RESULT);

    ctx.onLoad({ id: AWEME });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(mockApi.parse).toHaveBeenCalledWith('https://www.douyin.com/video/' + AWEME);
  });
});
