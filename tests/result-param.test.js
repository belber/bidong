// 结果页必须「URL 自包含」：微信搜索爬虫/分享链接只能靠 URL 里的 bvid 打开页面，
// 依赖 globalData / storage 传参的话，爬虫看到的永远是空页面。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const homeJs = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/home/home.js'), 'utf8'
);

const CARD = {
  id: 6,
  bvid: 'BV1Nse466EsX',
  title: '【小视频】167-国贸街拍',
  up_name: '帅哥录屏',
  pubdate: 1789796701,
  cover_url: 'https://cos/bv.jpg',
  tags: [],
  origin: { account_name: '帅哥录屏', platform_label: '抖音', author_name: '李不然' }
};

describe('结果页 URL 自包含', () => {
  test('抖音走 platform=douyin&id= 打开，并带上平台去刷新', () => {
    const { ctx } = loadPage(PAGE);
    const refreshed = [];
    ctx.loadByPlatform = (platform, id, opts) =>
      refreshed.push({ platform, id, opts });

    ctx.onLoad({ platform: 'douyin', id: '7685688911658323392' });

    expect(refreshed).toHaveLength(1);
    expect(refreshed[0].platform).toBe('douyin');
    expect(refreshed[0].id).toBe('7685688911658323392');
  });

  test('首页跳结果页要带上 bvid', () => {
    expect(homeJs).toContain("'/pages/result/result?bvid=' + card.bvid");
  });

  test('带 bvid 打开时：先用手上的解析结果秒开，再按 bvid 刷新', () => {
    const { ctx, app } = loadPage(PAGE);
    app.globalData.pendingResult = CARD;
    const refreshed = [];
    ctx.loadByPlatform = (platform, id, opts) =>
      refreshed.push({ platform, id, opts });

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });

    expect(ctx.data.title).toBe('【小视频】167-国贸街拍');
    expect(refreshed).toHaveLength(1);
    expect(refreshed[0].platform).toBe('bilibili');
    expect(refreshed[0].id).toBe('BV1Nse466EsX');
    expect(refreshed[0].opts).toMatchObject({ silent: true });
  });

  test('手头的解析结果不是这一条时，不要拿它糊弄', () => {
    const { ctx, app } = loadPage(PAGE);
    app.globalData.pendingResult = Object.assign({}, CARD, { bvid: 'BVother' });
    const refreshed = [];
    ctx.loadByPlatform = (platform, id, opts) =>
      refreshed.push({ platform, id, opts });

    ctx.onLoad({ bvid: 'BV1Nse466EsX' });

    expect(ctx.data.title).toBe('');
    expect(refreshed[0].opts).not.toMatchObject({ silent: true });
  });

  test('没带 bvid 时仍然沿用手上的解析结果（老路径不能坏）', () => {
    const { ctx, app } = loadPage(PAGE);
    app.globalData.pendingResult = CARD;
    ctx.loadByPlatform = () => { throw new Error('不该发请求'); };

    ctx.onLoad({});

    expect(ctx.data.title).toBe('【小视频】167-国贸街拍');
  });
});

describe('结果页标题与分享', () => {
  test('渲染后把导航标题设成视频标题（搜索结果相关性）', () => {
    const { ctx, titles } = loadPage(PAGE);
    ctx.applyResult(CARD);
    expect(titles.some(t => t.includes('【小视频】167-国贸街拍'))).toBe(true);
    expect(titles.some(t => t.includes('B站视频下载'))).toBe(true);
  });

  test('抖音内容页标题带「抖音视频下载」，不带 B站 词', () => {
    const { ctx, titles } = loadPage(PAGE);
    ctx.applyResult({ ...CARD, platform: 'douyin', bvid: '7698027358250432602' });
    const last = titles[titles.length - 1];
    expect(last).toContain('抖音视频下载');
    expect(last).not.toContain('B站');
  });

  test('分享卡片指向这条视频，而不是笼统的首页', () => {
    const { ctx } = loadPage(PAGE);
    ctx.applyResult(CARD);
    const share = ctx.onShareAppMessage();
    expect(share.path).toBe('/pages/result/result?bvid=BV1Nse466EsX');
    expect(share.title).toContain('【小视频】167-国贸街拍');
    expect(share.imageUrl).toBe('https://cos/bv.jpg');
  });

  test('朋友圈分享也带上这条视频', () => {
    const { ctx } = loadPage(PAGE);
    ctx.applyResult(CARD);
    expect(typeof ctx.onShareTimeline).toBe('function');
    const timeline = ctx.onShareTimeline();
    expect(timeline.query).toContain('bvid=BV1Nse466EsX');
  });
});
