// 广告位只保留一个，但位置要放在首屏/内容交界处，别埋在整页最底部。
const fs = require('fs');
const path = require('path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '../miniprogram', rel), 'utf8');
const indexOf = (text, needle) => {
  const at = text.indexOf(needle);
  expect(at).toBeGreaterThan(-1);
  return at;
};

describe('广告位位置', () => {
  test('首页广告在「如何获取链接」引导卡之后、页脚之前', () => {
    const wxml = read('pages/home/home.wxml');
    const ad = indexOf(wxml, 'class="ad-banner"');
    expect(ad).toBeGreaterThan(indexOf(wxml, 'class="guide-card"'));
    expect(ad).toBeLessThan(indexOf(wxml, 'class="home-footer-note"'));
  });

  test('结果页广告在媒体卡之后、文本卡之前', () => {
    const wxml = read('pages/result/result.wxml');
    const ad = indexOf(wxml, 'class="ad-banner"');
    expect(ad).toBeGreaterThan(indexOf(wxml, '<text>媒体</text>'));
    expect(ad).toBeLessThan(indexOf(wxml, '<text>文本</text>'));
  });
});
