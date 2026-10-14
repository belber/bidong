const { extractBiliLink, extractDouyinLink, extractLink } = require('./parse');

describe('extractBiliLink', () => {
  test('识别完整视频链接', () => {
    expect(extractBiliLink('https://www.bilibili.com/video/BV1xx411c7mD')).toEqual({
      kind: 'video',
      bvid: 'BV1xx411c7mD',
      url: 'https://www.bilibili.com/video/BV1xx411c7mD'
    });
  });

  test('识别短链', () => {
    expect(extractBiliLink('https://b23.tv/2g9l5YF')).toEqual({
      kind: 'short',
      url: 'https://b23.tv/2g9l5YF'
    });
  });

  test('非 B站 返回 null', () => {
    expect(extractBiliLink('https://v.douyin.com/iRNBho6/')).toBeNull();
  });
});

describe('extractDouyinLink', () => {
  test('识别短链', () => {
    expect(extractDouyinLink('7.43 复制打开抖音，看看【木鱼水心】 https://v.douyin.com/iRNBho6/')).toEqual({
      kind: 'short',
      url: 'https://v.douyin.com/iRNBho6/'
    });
  });

  test('识别作品页链接并归一化成 video', () => {
    expect(extractDouyinLink('https://www.douyin.com/video/7685688911658323392')).toEqual({
      kind: 'video',
      awemeId: '7685688911658323392',
      url: 'https://www.douyin.com/video/7685688911658323392'
    });
  });

  test('图文用 note 路径保留', () => {
    expect(extractDouyinLink('https://www.douyin.com/note/7300000000000000000')).toEqual({
      kind: 'note',
      awemeId: '7300000000000000000',
      url: 'https://www.douyin.com/note/7300000000000000000'
    });
  });

  test('分享页 slides 也要认', () => {
    const r = extractDouyinLink('https://www.iesdouyin.com/share/slides/7300000000000000000/');
    expect(r).toEqual({
      kind: 'short',
      url: 'https://www.iesdouyin.com/share/slides/7300000000000000000/'
    });
  });

  test('非抖音返回 null', () => {
    expect(extractDouyinLink('https://www.bilibili.com/video/BV1xx411c7mD')).toBeNull();
  });
});

describe('extractLink', () => {
  test('一个入口认出两个平台', () => {
    expect(extractLink('https://www.bilibili.com/video/BV1xx411c7mD').platform).toBe('bilibili');
    expect(extractLink('https://v.douyin.com/iRNBho6/').platform).toBe('douyin');
    expect(extractLink('随便一段文字')).toBeNull();
    expect(extractLink('')).toBeNull();
  });

  test('抖音优先于 B站 判定（分享文案可能同时含两个链接时以先出现的平台为准）', () => {
    const r = extractLink('https://v.douyin.com/iRNBho6/');
    expect(r.platform).toBe('douyin');
    expect(r.link.url).toBe('https://v.douyin.com/iRNBho6/');
  });
});
