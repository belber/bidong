// 结果页被分享出去、或被微信搜索爬虫打开时没有登录态，
// 必须退回免登录的公开信息渲染——否则页面是空的，既没法收录也没法让人看。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

const realApi = jest.requireActual('../miniprogram/utils/api.js');

const mockApi = {
  parse: jest.fn(),
  getPublicCard: jest.fn(),
  getPublicConfig: jest.fn(() => Promise.resolve({})),
  mediaSize: jest.fn(() => Promise.resolve({})),
  reportDownloadEvent: jest.fn(() => Promise.resolve({})),
  // 页面会把 cover_url / 头像过一遍地址解析：公开信息里的绝对地址原样返回
  resolveMediaUrl: realApi.resolveMediaUrl
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

    expect(mockApi.getPublicCard).toHaveBeenCalledWith('BV1Nse466EsX', 'bilibili');
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
    expect(wxml).toContain('{{!isDouyin && media.watermarked && !publicView}}');
    expect(wxml).toContain('{{!isDouyin && media.audio && !publicView}}');
    expect(wxml).toContain('wx:if="{{!publicView && !isDouyin}}"');
  });
});

describe('抖音图文提示', () => {
  const wxml = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
  );

  test('拿不到图片时说明是图文作品，而不是「图不存在」', () => {
    expect(wxml).toContain('{{isDouyin && isNote && !imageCount}}');
    expect(wxml).toContain('这是抖音图文作品，图片暂不支持保存');
    expect(wxml).not.toContain('这张图不存在');
  });
});

describe('抖音下载的进度反馈', () => {
  const wxml = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
  );
  const js = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
  );

  test('视频、音频、图文三种都有进度条', () => {
    // 视频走相册保存（自己的 downloading/activeKind）
    expect(wxml).toContain('{{downloading && activeKind === \'video\'}}');
    expect(wxml).toContain('width: {{downloadProgress}}%');
    // 音频走导出状态机（和 B站 同一套）
    expect(wxml).toContain("{{exports.audio.state === 'downloading'}}");
    // 图文按张数推进
    expect(wxml).toContain('{{savingImages}}');
    expect(wxml).toContain('width: {{imagePercent}}%');
  });

  test('抖音下载要设 activeKind，否则百分比和进度条都不会显示', () => {
    const body = js.slice(js.indexOf('onDownloadDouyin(e)'), js.indexOf('onSaveImages()'));
    expect(body).toContain('this.setData({ activeKind: kind })');
  });
});

describe('抖音图文通过服务端数据保存', () => {
  const js = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
  );
  const api = fs.readFileSync(
    path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8'
  );

  test('API 客户端提供图文数据接口', () => {
    expect(api).toContain('douyinImages(id)');
    expect(api).toContain("'/api/cards/' + id + '/images-data'");
  });

  test('保存图片使用服务端数据、base64 和本地文件', () => {
    const block = js.slice(js.indexOf('onSaveImages()'), js.indexOf('onOpenDouyin()'));
    expect(block).toContain('api.douyinImages(this.data.cardId)');
    expect(block).toContain('wx.base64ToArrayBuffer');
    expect(js).toContain('writeFile');
    expect(js).toContain('wx.saveImageToPhotosAlbum');
    expect(block).not.toContain("api.downloadUrl(this.data.cardId, 'image')");
  });

  test('保存失败上报准确的微信错误并处理相册权限', () => {
    const block = js.slice(js.indexOf('onSaveImages()'), js.indexOf('onOpenDouyin()'));
    expect(block).toContain('wx_err_msg');
    expect(js).toContain("scope.writePhotosAlbum");
    expect(js).toContain('wx.openSetting');
  });
});

describe('抖音音频走导出状态机（和 B站 一致）', () => {
  const wxml = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
  );
  const js = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
  );

  // 相册只收视频：MP3 走 saveVideoToPhotosAlbum 会报 invalid file type
  test('抖音音频不再用相册保存，改走 onExportTap', () => {
    const start = wxml.indexOf('isDouyin && media.audio');
    const row = wxml.slice(start, wxml.indexOf('</view>', wxml.indexOf('export-progress', start)));
    expect(row).toContain('bindtap="onExportTap"');
    expect(row).not.toContain('onDownloadDouyin');
    expect(row).not.toContain('saveVideoToPhotosAlbum');
    expect(row).toContain("exports.audio.state === 'ready' ? '保存'");
  });

  test('抖音视频仍然走相册保存', () => {
    const start = wxml.indexOf('isDouyin && media.clean');
    const row = wxml.slice(start, wxml.indexOf('isDouyin && media.audio'));
    expect(row).toContain('bindtap="onDownloadDouyin"');
    expect(row).toContain("data-kind=\"video\"");
  });

  test('exportRequest 对抖音取 CDN 直链，而不是后端代理', () => {
    const body = js.slice(js.indexOf('exportRequest(kind)'), js.indexOf('exportName(kind)'));
    expect(body).toContain('this.data.isDouyin');
    expect(body).toContain("api.downloadUrl(this.data.cardId, 'audio')");
    expect(body).toContain('configuredCandidates');
  });

  test('onDownloadDouyin 拒绝音频，避免走回相册那条路', () => {
    const body = js.slice(js.indexOf('onDownloadDouyin(e)'), js.indexOf('onSaveImages()'));
    expect(body).toContain("if (kind !== 'video')");
  });
});

describe('结果页抖音号', () => {
  const wxml = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
  );
  const js = fs.readFileSync(
    path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
  );

  test('抖音号取自后端 author_id（曾误读 up_mid，字段没暴露导致永远为空）', () => {
    expect(js).toContain('douyinId: r.author_id');
    expect(js).not.toContain('douyinId: r.up_mid');
    expect(wxml).toContain('抖音号');
  });
});
