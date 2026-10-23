// 首页排版契约：解析按钮 / 广告与「如何获取链接」卡片之间的间距，
// 以及广告容器不写死高度（真机素材更扁时会在广告下方空出一条）。
const fs = require('fs');
const path = require('path');

const WXSS = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/home/home.wxss'),
  'utf8'
);

function ruleFor(selector) {
  const start = WXSS.indexOf(selector);
  expect(start).toBeGreaterThan(-1);
  const body = WXSS.slice(start);
  return body.slice(0, body.indexOf('}'));
}

describe('首页排版', () => {
  test('「如何获取链接」卡片与解析按钮之间留够间距', () => {
    expect(ruleFor('.guide-card {')).toMatch(/margin-top:\s*28rpx/);
  });

  test('广告紧跟在「如何获取链接」卡片下方，留一点间距', () => {
    expect(ruleFor('.ad-banner {')).toMatch(/margin-top:\s*28rpx/);
  });

  test('广告容器不再按固定比例预留高度', () => {
    const rule = ruleFor('.ad-banner {');
    expect(rule).not.toMatch(/height:\s*calc\(/);
    expect(rule).toMatch(/height:\s*auto/);
  });

  test('解析按钮只比常态略高一档，不做成突兀的色块', () => {
    const rule = ruleFor('.parse-btn {');
    expect(rule).toMatch(/min-height:\s*96rpx/);
    expect(rule).toMatch(/padding:\s*12rpx 0 14rpx/);
    expect(rule).toMatch(/font-size:\s*32rpx/);
  });
});
