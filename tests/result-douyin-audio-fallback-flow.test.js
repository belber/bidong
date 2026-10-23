// 抖音音频是 CDN 直链，域名没登记进微信白名单时小程序内下不动。
// 这里跑真实流程（不打桩业务方法），确认「按钮变重试 + 弹复制链接弹窗」确实发生。
const path = require('path');
const { loadPage } = require('./helpers/page.js');
const { initialExports } = require('../miniprogram/utils/exportState.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');

const realApi = jest.requireActual('../miniprogram/utils/api.js');
const mockApi = {
  downloadUrl: jest.fn(),
  download: jest.fn(),
  authHeader: () => ({}),
  reportDownloadEvent: jest.fn(() => Promise.resolve()),
  resolveMediaUrl: realApi.resolveMediaUrl
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

const AUDIO_URL = 'https://sf6-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/a.mp3';
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function douyinCtx() {
  const { page, ctx } = loadPage(PAGE);
  ctx.setData({
    isDouyin: true,
    cardId: 17,
    bvid: '7698027358250432602',
    title: '图文标题',
    exports: initialExports()
  });
  return { page, ctx };
}

describe('抖音音频域名未配置时的兜底', () => {
  beforeEach(() => {
    mockApi.downloadUrl.mockReset();
    mockApi.reportDownloadEvent.mockClear();
  });

  test('没有任何已配置候选：直接弹「换一种方式保存」，复制直链', async () => {
    mockApi.downloadUrl.mockResolvedValue({
      candidates: [{ url: AUDIO_URL, host: 'sf6-cdn-tos.douyinstatic.com', configured: false }]
    });
    const { page, ctx } = douyinCtx();

    page.startExport.call(ctx, 'audio');
    await tick();
    await tick();

    expect(ctx.data.fallbackVisible).toBe(true);
    expect(ctx.data.fallbackUrl).toBe(AUDIO_URL);
    expect(ctx.data.exports.audio.state).toBe('failed');
    expect(mockApi.reportDownloadEvent).toHaveBeenCalled();
    const reported = mockApi.reportDownloadEvent.mock.calls.map((c) => c[0]);
    expect(reported.some((r) => r.error_type === 'domain_not_configured')).toBe(true);
  });

  test('微信真实报 url not in domain list：同样弹窗，并保留「重试」', async () => {
    mockApi.downloadUrl.mockResolvedValue({
      candidates: [{ url: AUDIO_URL, host: 'sf6-cdn-tos.douyinstatic.com', configured: true }]
    });
    const { page, ctx } = douyinCtx();
    global.wx.downloadFile = (opts) => {
      opts.fail({ errMsg: 'downloadFile:fail url not in domain list' });
      return { onProgressUpdate() {} };
    };

    page.startExport.call(ctx, 'audio');
    await tick();
    await tick();

    expect(ctx.data.fallbackVisible).toBe(true);
    expect(ctx.data.fallbackUrl).toBe(AUDIO_URL);
    expect(ctx.data.exports.audio.state).toBe('failed');
    const reported = mockApi.reportDownloadEvent.mock.calls.map((c) => c[0]);
    expect(reported.some((r) => r.error_type === 'domain_not_configured')).toBe(true);
  });
});
