const fs = require('fs');
const path = require('path');

function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
}

const wxml = read('miniprogram/pages/result/result.wxml');
const js = read('miniprogram/pages/result/result.js');
const wxss = read('miniprogram/pages/result/result.wxss');

describe('解析结果页 · 视频出处区块', () => {
  test('整块以 origin 为开关，其他 UP 主的视频不会渲染', () => {
    expect(wxml).toContain('wx:if="{{origin}}"');
  });

  test('标题带上账号名与粉丝原话', () => {
    expect(wxml).toContain('{{origin.accountName}}');
    expect(wxml).toContain('原up主是谁');
    expect(wxml).toContain('粉丝专属');
  });

  test('字段沿用 字段名/值 结构', () => {
    expect(wxml).toContain('原平台');
    expect(wxml).toContain('{{origin.platformText}}');
    expect(wxml).toContain('原up主');
    expect(wxml).toContain('{{origin.authorText}}');
  });

  test('复制原up账号和现有「复制」用同一处理方式', () => {
    expect(wxml).toContain('class="action"');
    expect(wxml).toContain('bindtap="onCopyAuthorName"');
    expect(wxml).toContain('复制原up账号');
    expect(js).toContain('onCopyAuthorName');
    expect(js).toContain('wx.setClipboardData');
    expect(js).toContain('copyText');
    // 复制的是昵称，不是主页链接
    expect(js).not.toContain('authorUrl');
  });

  test('查不到出处时给出「整理中」提示', () => {
    expect(wxml).toContain('origin.pending');
    expect(wxml).toContain('这条的出处还在整理');
  });

  test('头像与卡片样式已定义', () => {
    expect(wxml).toContain('origin.accountAvatarUrl');
    expect(wxss).toContain('.source-card');
    expect(wxss).toContain('.src-avatar');
  });

  test('结果页把后端返回的 origin 映射成视图模型', () => {
    expect(js).toContain("require('../../utils/origin.js')");
    expect(js).toContain('mapOrigin');
  });
});
