// 结果页加载不再用系统黑色「加载中」，改成自绘的进度条卡片（纯 CSS，不依赖定时器）。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const WXML = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);
const JS = fs.readFileSync(PAGE, 'utf8');

describe('结果页倒计时加载', () => {
  test('显示 / 隐藏进度卡片', () => {
    const { ctx } = loadPage(PAGE);

    ctx.showCountdownLoading('解析中');
    expect(ctx.data.loadingVisible).toBe(true);
    expect(ctx.data.loadingText).toBe('解析中');

    ctx.hideCountdownLoading();
    expect(ctx.data.loadingVisible).toBe(false);
  });

  test('进度条完全由 CSS 动画驱动，不再用 setInterval', () => {
    const block = JS.slice(JS.indexOf('showCountdownLoading('), JS.indexOf('applyResult('));
    expect(block).not.toContain('setInterval');
    expect(block).not.toContain('clearInterval');
  });

  test('loadByPlatform 不再调用系统 showLoading', () => {
    const block = JS.slice(
      JS.indexOf('loadByPlatform(platform, videoId, opts)'),
      JS.indexOf('showCountdownLoading(text)')
    );
    expect(block).toContain("this.showCountdownLoading('解析中')");
    expect(block).not.toContain('wx.showLoading');
    expect(WXML).toContain('class="countdown-mask"');
    expect(WXML).toContain('countdown-track');
    expect(WXML).toContain('countdown-bar');
  });
});
