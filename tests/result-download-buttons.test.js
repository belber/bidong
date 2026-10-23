// 媒体下载/保存按钮要一眼能看到：实心胶囊按钮，而不是一行粉色小字。
const fs = require('fs');
const path = require('path');

const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);
const wxss = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxss'), 'utf8'
);

describe('媒体下载按钮', () => {
  test('视频 / 音频 / 图片的主操作都用 download-btn', () => {
    const count = (wxml.match(/download-btn/g) || []).length;
    expect(count).toBeGreaterThanOrEqual(6); // 抖音视频/音频/图片 + B站视频x2/音频
  });

  test('按钮是实心胶囊，不是纯文字链接', () => {
    const start = wxss.indexOf('.action.download-btn');
    expect(start).toBeGreaterThan(-1);
    const rule = wxss.slice(start, wxss.indexOf('}', start));
    expect(rule).toContain('min-width: 132rpx');
    expect(rule).toContain('height: 56rpx');
    expect(rule).toContain('background: #fb7299');
    expect(rule).toContain('color: #ffffff');
    expect(rule).toContain('border-radius: 28rpx');
  });

  test('保存中的按钮文案保持短，不撑成一大块', () => {
    expect(wxml).toContain("{{savingImages ? '保存中' : '保存全部'}}");
    expect(wxml).not.toContain("savingImages ? (imageStatus");
  });
});
