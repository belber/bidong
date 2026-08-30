const { extractBiliLink } = require('../miniprogram/utils/parse.js');

describe('extractBiliLink', () => {
  test('从完整视频链接提取 bvid', () => {
    const r = extractBiliLink('https://www.bilibili.com/video/BV1BE4U6BEg8');
    expect(r).toEqual({
      kind: 'video',
      bvid: 'BV1BE4U6BEg8',
      url: 'https://www.bilibili.com/video/BV1BE4U6BEg8'
    });
  });

  test('从纯 BV 号识别并补全链接', () => {
    const r = extractBiliLink('BV1BE4U6BEg8');
    expect(r).toEqual({
      kind: 'video',
      bvid: 'BV1BE4U6BEg8',
      url: 'https://www.bilibili.com/video/BV1BE4U6BEg8'
    });
  });

  test('识别 b23.tv 短链并交给后端解析', () => {
    const r = extractBiliLink('https://b23.tv/AbC123');
    expect(r).toEqual({
      kind: 'short',
      url: 'https://b23.tv/AbC123'
    });
  });

  test('从混合文本中提取链接', () => {
    const r = extractBiliLink('这个视频好看 BV1BE4U6BEg8 大家快看');
    expect(r.kind).toBe('video');
    expect(r.bvid).toBe('BV1BE4U6BEg8');
  });

  test('非 B站链接返回 null', () => {
    expect(extractBiliLink('https://www.youtube.com/watch?v=abc')).toBeNull();
  });

  test('空文本返回 null', () => {
    expect(extractBiliLink('')).toBeNull();
    expect(extractBiliLink('   ')).toBeNull();
  });
});
