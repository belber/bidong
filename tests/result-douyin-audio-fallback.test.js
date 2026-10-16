// 抖音音频是 CDN 直链，走 wx.downloadFile；域名没登记进微信白名单时会失败。
// 这种失败和 B站 视频一样，不该只弹「下载失败」，而要弹「换一种方式保存」让用户复制链接。
const fs = require('fs');
const path = require('path');

const js = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.js'), 'utf8'
);

describe('抖音音频下载遇到域名未配置', () => {
  test('复用微信域名错误识别，不自己写正则', () => {
    expect(js).toContain('classifyError');
    expect(js).toContain("classifyError(null, err) === 'domain_not_configured'");
  });

  test('兜底是个独立方法，音频和视频共用', () => {
    expect(js).toContain('openExportFallback');
    expect(js).toContain('openExportFallback(kind)');
  });

  test('一个已配置候选都没有时也走兜底，而不是只报「获取下载地址失败」', () => {
    expect(js).toContain("err.code = 'domain_not_configured'");
  });

  test('兜底复制的是重新取到的新直链（抖音直链有时效）', () => {
    const block = js.slice(js.indexOf('openExportFallback(kind) {'), js.indexOf('onCloseFallback'));
    expect(block).toContain('api.downloadUrl(this.data.cardId, kind)');
    expect(block).toContain('this.openFallback(');
  });

  test('音频失败仍保留「重试」按钮，兜底是额外的一条路', () => {
    const block = js.slice(js.indexOf('openExportFallback(kind) {'), js.indexOf('onCloseFallback'));
    expect(block).toContain("failExport(this.data.exports, kind)");
  });

  test('只对音频兜底，B站 音频仍走后端中转不弹弹窗', () => {
    const exportBlock = js.slice(js.indexOf('startExport(kind) {'), js.indexOf('shareExport(kind) {'));
    expect(exportBlock).toContain("kind === 'audio'");
    expect(exportBlock).toContain('this.data.isDouyin');
  });
});
