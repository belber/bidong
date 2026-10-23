const fs = require('fs');
const path = require('path');

const cases = [
  ['home/home.json', 'B站视频下载 · 抖音视频下载 · 视频下载 · 视频提取'],
  ['result/result.json', '视频下载 / 视频提取结果'],
  ['collect/collect.json', '视频下载记录'],
  ['help/help.json', 'B站视频提取 · 抖音视频提取 · 视频下载'],
  ['about/about.json', '视频下载 · 视频提取 · B站 / 抖音']
];

describe('searchable page metadata', () => {
  test.each(cases)('%s has a search-friendly title', (file, expected) => {
    const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../miniprogram/pages', file), 'utf8'));
    expect(config.navigationBarTitleText).toBe(expected);
  });

  test('help page answers common search intents', () => {
    const html = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/help/help.wxml'), 'utf8');
    [
      '怎么下载 / 提取 B站视频？',
      '怎么保存视频封面？',
      '怎么导出视频音频？',
      '怎么导出字幕？',
      '怎么提取视频？',
      '支持抖音视频下载吗？'
    ].forEach((text) => {
      expect(html).toContain(text);
    });
  });
});
