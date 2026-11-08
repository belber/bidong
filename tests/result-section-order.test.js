// 结果页区块顺序：出处（有数据才显示）→ 基本信息 → 媒体 → 广告 → 文本
const fs = require('fs');
const path = require('path');

const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

const at = (needle) => {
  const index = wxml.indexOf(needle);
  expect(index).toBeGreaterThan(-1);
  return index;
};

describe('结果页区块顺序', () => {
  test('出处 → 基本信息 → 媒体 → 广告 → 文本', () => {
    const order = [
      at('class="card source-card"'),
      at('<text>基本信息</text>'),
      at('<text>媒体</text>'),
      at('class="ad-banner"'),
      at('<text>文本</text>')
    ];
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  test('不再渲染统计区块', () => {
    expect(wxml).not.toContain('<text>数据</text>');
    expect(wxml).not.toContain('stats-box');
  });

  test('出处区块只在有 origin 时展示', () => {
    expect(wxml).toContain('<view class="card source-card" wx:if="{{origin}}">');
  });
});
