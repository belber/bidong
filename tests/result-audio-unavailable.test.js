// B站 对部分视频（长视频等）不提供独立音频轨，接口会返回 404。
// 这种情况不该让用户对着按钮反复重试，而要告诉他"声音在视频里"。
const fs = require('fs');
const path = require('path');

const js = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
);
const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

describe('没有独立音频轨的视频', () => {
  test('音频 404 时记住这个状态，并提示去下视频', () => {
    expect(js).toContain("kind === 'audio' && res.statusCode === 404");
    expect(js).toContain('audioUnavailable: true');
    expect(js).toContain('这条视频没有单独的音轨，可下载视频');
  });

  test('初始状态是"可用"，不误伤正常视频', () => {
    expect(js).toMatch(/audioUnavailable: false/);
  });

  test('页面把死按钮换成指路文案', () => {
    expect(wxml).toContain('wx:if="{{!audioUnavailable}}"');
    expect(wxml).toContain('这条视频没有单独的音轨，下载上面的「视频」即可');
  });
});
