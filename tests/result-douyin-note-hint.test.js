// 图文作品的图片和音频是两个独立下载项，媒体区必须先说清楚「分开下载」，
// 否则用户会以为点一次就能拿到整条作品。
const fs = require('fs');
const path = require('path');

const wxml = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);
const wxss = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxss'), 'utf8'
);

// 媒体卡片：从「媒体」标题到「文本」卡片之间
const mediaCard = wxml.slice(wxml.indexOf('<text>媒体</text>'), wxml.indexOf('<text>文本</text>'));

describe('抖音图文的媒体区说明', () => {
  test('说明落在媒体区块里，且只在抖音图文、非公开视图显示', () => {
    expect(mediaCard).toContain('media-hint');
    expect(mediaCard).toContain('{{isDouyin && isNote && !publicView}}');
    expect(mediaCard).toContain('和音频需要分开下载');
  });

  test('带图片数量，数量未知时不说「0 张」', () => {
    expect(mediaCard).toContain("{{imageCount ? imageCount + ' 张图片' : '图片'}}");
    expect(mediaCard).not.toContain('{{imageCount}} 张图片和音频');
  });

  test('提示有一行自己的样式，不挤在 label 里', () => {
    expect(wxss).toContain('.media-hint {');
  });
});
