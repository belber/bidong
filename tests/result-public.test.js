// 结果页被分享出去、或被微信搜索爬虫打开时没有登录态，
// 必须退回免登录的公开信息渲染——否则页面是空的，既没法收录也没法让人看。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

const mockApi = {
  parse: jest.fn(),
  getPublicCard: jest.fn(),
  getPublicConfig: jest.fn(() => Promise.resolve({})),
  mediaSize: jest.fn(() => Promise.resolve({})),
  reportDownloadEvent: jest.fn(() => Promise.resolve({}))
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

const PUBLIC_CARD = {
  bvid: 'BV1Nse466EsX',
  title: '【小视频】167-国贸街拍',
  up_name: '帅哥录屏',
  partition: '旅游出行',
  pubdate: 1789796701,
  cover_url: 'https://cos/bv.jpg',
  source_url: 'https://www.bilibili.com/video/BV1Nse466EsX',
  origin: {
    account_name: '帅哥录屏',
    platform_label: '抖音',
    author_name: '李不然',
    author_handle: 'luke0123'
  }
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  mockApi.parse.mockReset();
  mockApi.getPublicCard.mockReset();
});

describe('未登录时退回公开信息', () => {
  test('解析接口报"未登录"时，用公开接口把内容渲染出来', async () => {
    mockApi.parse.mockRejectedValue(new Error('获取微信登录凭证失败'));
    mockApi.getPublicCard.mockResolvedValue(PUBLIC_CARD);
    const { ctx } = loadPage(PAGE);

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });
    await tick();

    expect(mockApi.getPublicCard).toHaveBeenCalledWith('BV1Nse466EsX');
    expect(ctx.data.title).toBe('【小视频】167-国贸街拍');
    expect(ctx.data.upName).toBe('帅哥录屏');
    expect(ctx.data.publicView).toBe(true);
    expect(ctx.data.origin.authorText).toBe('@李不然');
    expect(ctx.data.origin.copyText).toBe('luke0123');
  });

  test('登录态失效（401）也走公开信息', async () => {
    const err = new Error('登录态无效或已过期');
    err.statusCode = 401;
    mockApi.parse.mockRejectedValue(err);
    mockApi.getPublicCard.mockResolvedValue(PUBLIC_CARD);
    const { ctx, toasts } = loadPage(PAGE);

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });
    await tick();

    expect(ctx.data.publicView).toBe(true);
    expect(toasts).toEqual([]); // 有内容可看就别弹错误
  });

  test('视频本身有问题（404）时不兜底，正常报错', async () => {
    const err = new Error('视频不存在或已被删除');
    err.statusCode = 404;
    mockApi.parse.mockRejectedValue(err);
    const { ctx, toasts } = loadPage(PAGE);

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });
    await tick();

    expect(mockApi.getPublicCard).not.toHaveBeenCalled();
    expect(ctx.data.publicView).toBe(false);
    expect(toasts).toContain('视频不存在或已被删除');
  });

  test('正常登录用户不受影响（publicView 保持 false）', async () => {
    mockApi.parse.mockResolvedValue(Object.assign({ id: 6, stats: {} }, PUBLIC_CARD));
    const { ctx } = loadPage(PAGE);

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });
    await tick();

    expect(ctx.data.publicView).toBe(false);
    expect(mockApi.getPublicCard).not.toHaveBeenCalled();
  });
});

describe('公开视图的界面约束', () => {
  test('页面有访客提示，且下载/导出入口按 publicView 隐藏', () => {
    expect(wxml).toContain('visitor-tip');
    expect(wxml).toContain('以访客身份查看');
    expect(wxml).toContain('{{media.watermarked && !publicView}}');
    expect(wxml).toContain('{{media.audio && !publicView}}');
    expect(wxml).toContain('wx:if="{{!publicView}}"');
  });
});
