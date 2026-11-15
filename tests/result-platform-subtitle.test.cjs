const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const js = fs.readFileSync('miniprogram/pages/result/result.js', 'utf8');
const wxml = fs.readFileSync('miniprogram/pages/result/result.wxml', 'utf8');
test('文案完成不能覆盖平台字幕', () => {
  assert(!js.includes('this.setData({subtitles, subPreview:subtitles.slice(0,5)})'));
});
test('字幕导出始终使用平台导出接口', () => {
  assert.match(js, /if \(kind === 'subtitle'\) return api.exportFile\(this.data.cardId, 'srt'\);/);
});
test('平台没有字幕时不展示字幕行', () => {
  assert.match(wxml, /class="field export-field" wx:if="{{subtitles.length}}">\s*<text class="label">字幕/);
  assert(!wxml.includes('wx:else>无字幕'));
});
