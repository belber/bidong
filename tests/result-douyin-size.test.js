// 抖音结果页的「视频 / 音频」行也要像 B站 那样带上文件大小。
// B站 的大小来自 /media-size 的 watermarked / clean / audio，抖音来自 video / audio。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

const realApi = jest.requireActual('../miniprogram/utils/api.js');
const mockApi = {
  mediaSize: jest.fn(() => Promise.resolve({})),
  resolveMediaUrl: realApi.resolveMediaUrl
};
jest.mock('../miniprogram/utils/api.js', () => mockApi);

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

// 抖音两张媒体卡：视频行 → 音频行 → 图文行
const videoRow = wxml.slice(
  wxml.indexOf('isDouyin && media.clean'), wxml.indexOf('isDouyin && media.audio')
);
const audioRow = wxml.slice(
  wxml.indexOf('isDouyin && media.audio'), wxml.indexOf('isDouyin && isNote')
);

describe('抖音结果页的媒体大小', () => {
  beforeEach(() => {
    mockApi.mediaSize.mockReset();
    mockApi.mediaSize.mockResolvedValue({});
  });

  test('mediaSize 的 video / audio 换算成和 B站 一样的「约 xx MB」', async () => {
    mockApi.mediaSize.mockResolvedValue({ video: 1504900, audio: 1048576 });
    const { page, ctx } = loadPage(PAGE);

    page.loadMediaSize.call(ctx, 7);
    await tick();

    expect(mockApi.mediaSize).toHaveBeenCalledWith(7);
    expect(ctx.data.mediaSize).toEqual({ video: '约 1.4 MB', audio: '约 1.0 MB' });
  });

  test('抖音视频行把大小显示在描述位，取不到时回落成原描述', () => {
    expect(videoRow).toContain("mediaSize.video || '无水印，直接在手机上保存'");
  });

  test('抖音音频行同理', () => {
    expect(audioRow).toContain("mediaSize.audio || '原声 / BGM'");
  });

  test('B站 三行的键名不变（watermarked / clean / audio）', async () => {
    mockApi.mediaSize.mockResolvedValue({ watermarked: 1048576, clean: 2097152, audio: 524288 });
    const { page, ctx } = loadPage(PAGE);

    page.loadMediaSize.call(ctx, 8);
    await tick();

    expect(ctx.data.mediaSize.watermarked).toBe('约 1.0 MB');
    expect(ctx.data.mediaSize.clean).toBe('约 2.0 MB');
    expect(ctx.data.mediaSize.audio).toBe('约 512.0 KB');
  });
});
