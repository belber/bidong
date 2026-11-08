// 首页 / 收藏夹 / 我的导航栏统一带「视频下载」关键词。
const fs = require('fs');
const path = require('path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '../miniprogram', rel), 'utf8');

describe('自定义导航栏标题', () => {
  test('首页使用「壁咚咚藏链阁·视频下载」并启用紧凑字号', () => {
    const wxml = read('pages/home/home.wxml');
    expect(wxml).toContain('title="壁咚咚藏链阁·视频下载"');
    expect(wxml).toContain('compact="{{true}}"');
  });

  test('收藏夹和我的页也使用同一标题', () => {
    const js = read('components/navbar/navbar.js');
    expect(js).toContain("value: '壁咚咚藏链阁'");
    ['pages/collect/collect.wxml', 'pages/mine/mine.wxml'].forEach((file) => {
      const wxml = read(file);
      expect(wxml).toContain('title="壁咚咚藏链阁·视频下载"');
      expect(wxml).toContain('compact="{{true}}"');
    });
  });

  test('长标题有紧凑样式和省略兜底', () => {
    const wxss = read('components/navbar/navbar.wxss');
    expect(wxss).toContain('.brand-name.compact');
    expect(wxss).toContain('text-overflow: ellipsis');
    expect(wxss).toContain('font-size: 28rpx');
  });
});
