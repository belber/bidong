// 首页默认把「如何获取链接」收起成一行，保证广告落在首屏；点开再看完整引导。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/home/home.js');
const WXML = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/home/home.wxml'), 'utf8'
);

describe('首页引导折叠', () => {
  test('默认收起，只露出一行摘要', () => {
    const { ctx } = loadPage(PAGE);
    expect(ctx.data.guideExpanded).toBe(false);
    expect(WXML).toContain('wx:if="{{!guideExpanded}}"');
    expect(WXML).toContain('分享 → 复制链接，或 B站评论 @壁咚咚私藏');
  });

  test('两种方式藏在展开区块里', () => {
    const expanded = WXML.indexOf('wx:if="{{guideExpanded}}"');
    expect(expanded).toBeGreaterThan(-1);
    expect(expanded).toBeLessThan(WXML.indexOf('方式 1 ·'));
    expect(expanded).toBeLessThan(WXML.indexOf('方式 2 ·'));
  });

  test('点标题可以来回切换', () => {
    const { ctx } = loadPage(PAGE);
    ctx.onToggleGuide();
    expect(ctx.data.guideExpanded).toBe(true);
    ctx.onToggleGuide();
    expect(ctx.data.guideExpanded).toBe(false);
  });
});
