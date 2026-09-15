const fs = require('fs');
const path = require('path');

const cases = [
  ['home/home.json', 'B站视频链接解析 · 壁咚咚藏链阁'],
  ['result/result.json', '视频封面/音频/字幕解析结果 · 壁咚咚藏链阁'],
  ['collect/collect.json', 'B站视频收藏整理 · 壁咚咚藏链阁'],
  ['help/help.json', 'B站视频链接解析使用帮助 · 壁咚咚藏链阁'],
  ['about/about.json', '关于 壁咚咚藏链阁 · B站视频收藏整理']
];

describe('searchable page metadata', () => {
  test.each(cases)('%s has a search-friendly title', (file, expected) => {
    const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../miniprogram/pages', file), 'utf8'));
    expect(config.navigationBarTitleText).toBe(expected);
  });

  test('help page answers common search intents', () => {
    const html = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/help/help.wxml'), 'utf8');
    [
      '怎么解析 B站视频链接？',
      '怎么保存视频封面？',
      '怎么导出视频音频？',
      '怎么导出字幕？',
      '怎么保存视频？'
    ].forEach((text) => {
      expect(html).toContain(text);
    });
  });
});
