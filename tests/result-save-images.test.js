// 抖音图文「保存全部」：网络那 1~2 秒里按钮还是可点的，用户连点会重复下载整组图片。
// 这里按真实调用链复现，确认守卫在请求前就生效，并验证图片数据只取一次。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');

const realApi = jest.requireActual('../miniprogram/utils/api.js');
const mockApi = {
  douyinImages: jest.fn(),
  reportDownloadEvent: jest.fn(() => Promise.resolve()),
  resolveMediaUrl: realApi.resolveMediaUrl
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

const IMAGES = [
  { index: 1, mime: 'image/jpeg', ext: 'jpg', base64: 'AAAA' },
  { index: 2, mime: 'image/jpeg', ext: 'jpg', base64: 'BBBB' },
  { index: 3, mime: 'image/jpeg', ext: 'jpg', base64: 'CCCC' }
];

const flush = async (times = 6) => {
  for (let i = 0; i < times; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
};

function preparePage() {
  const { page, ctx } = loadPage(PAGE);
  ctx.setData({
    isDouyin: true,
    isNote: true,
    cardId: 17,
    bvid: '7698027358250432602',
    imageCount: IMAGES.length,
    savingImages: false
  });
  const saved = [];
  global.wx.env = { USER_DATA_PATH: '/tmp' };
  global.wx.base64ToArrayBuffer = () => new ArrayBuffer(8);
  global.wx.getSetting = (opts) => opts.success({ authSetting: { 'scope.writePhotosAlbum': true } });
  global.wx.getFileSystemManager = () => ({
    writeFile: (opts) => opts.success({})
  });
  global.wx.saveImageToPhotosAlbum = (opts) => {
    saved.push(opts.filePath);
    opts.success({});
  };
  return { page, ctx, saved };
}

describe('抖音图文保存全部', () => {
  beforeEach(() => {
    mockApi.douyinImages.mockReset();
    mockApi.reportDownloadEvent.mockClear();
  });

  test('请求还没回来时连点，只会跑一轮', async () => {
    let resolveFetch;
    mockApi.douyinImages.mockReturnValue(new Promise((resolve) => { resolveFetch = resolve; }));
    const { page, ctx, saved } = preparePage();

    page.onSaveImages.call(ctx);
    page.onSaveImages.call(ctx);
    page.onSaveImages.call(ctx);
    expect(mockApi.douyinImages).toHaveBeenCalledTimes(1);
    expect(ctx.data.savingImages).toBe(true);

    resolveFetch({ items: IMAGES, failed: [] });
    await flush();

    expect(saved).toHaveLength(IMAGES.length);
    expect(ctx.data.savingImages).toBe(false);
  });

  test('同一张卡片再次保存时复用已取到的图片数据', async () => {
    mockApi.douyinImages.mockResolvedValue({ items: IMAGES, failed: [] });
    const { page, ctx, saved } = preparePage();

    page.onSaveImages.call(ctx);
    await flush();
    expect(saved).toHaveLength(IMAGES.length);

    page.onSaveImages.call(ctx);
    await flush();

    expect(mockApi.douyinImages).toHaveBeenCalledTimes(1);
    expect(saved).toHaveLength(IMAGES.length * 2);
  });

  test('图片列表为空时不会把按钮卡在保存中', async () => {
    mockApi.douyinImages.mockResolvedValue({ items: [], failed: [] });
    const { page, ctx } = preparePage();

    page.onSaveImages.call(ctx);
    await flush();

    expect(ctx.data.savingImages).toBe(false);
    expect(ctx.data.imageProgress).toBe('');
  });
});
