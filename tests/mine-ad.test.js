// 我的页两条广告位：都在菜单卡片下方的留白里上下叠放——
// 上面那条是原来的位置（mine-top），下面那条是新加的（mine-bottom）。
// 该页没有列表内容、底部留白超过半屏，两条横幅补曝光；出错时只隐藏出错的那一条。
const path = require('path');
const fs = require('fs');
const { loadPage } = require('./helpers/page.js');
const ADS = require('../miniprogram/config/ads.js');

const MINE_JS = path.join(__dirname, '../miniprogram/pages/mine/mine.js');
const MINE_WXML = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/mine/mine.wxml'), 'utf8');

function adFail(slotKey) {
  return { currentTarget: { dataset: { slot: slotKey } } };
}

function adOffsets(wxml) {
  const offsets = [];
  for (let i = wxml.indexOf('<ad '); i >= 0; i = wxml.indexOf('<ad ', i + 1)) {
    offsets.push(i);
  }
  return offsets;
}

describe('我的页两个广告位', () => {
  test('页面数据里准备两条广告位，slotKey 与 unit-id 各自独立', () => {
    const { ctx } = loadPage(MINE_JS);

    expect([ctx.data.mineTop.slotKey, ctx.data.mineBottom.slotKey]).toEqual(['mine-top', 'mine-bottom']);
    // 页面只读 config，不写死 id：换广告位只改 config/ads.js
    expect(ctx.data.mineTop.unitId).toBe(ADS.MINE_BANNER_TOP);
    expect(ctx.data.mineBottom.unitId).toBe(ADS.MINE_BANNER_BOTTOM);
    expect(ctx.data.mineTop.adError).toBe(false);
    expect(ctx.data.mineBottom.adError).toBe(false);
  });

  test('上面那条加载失败，只隐藏上面那条', () => {
    const { ctx } = loadPage(MINE_JS);

    ctx.onAdError(adFail('mine-top'));

    expect(ctx.data.mineTop.adError).toBe(true);
    expect(ctx.data.mineBottom.adError).toBe(false);
  });

  test('下面那条加载失败，只隐藏下面那条', () => {
    const { ctx } = loadPage(MINE_JS);

    ctx.onAdError(adFail('mine-bottom'));

    expect(ctx.data.mineBottom.adError).toBe(true);
    expect(ctx.data.mineTop.adError).toBe(false);
  });

  test('WXML：两条横幅都排在菜单卡片下方，先旧位（上）后新位（下）', () => {
    const menuIdx = MINE_WXML.indexOf('class="menu card"');
    const [upperAd, lowerAd] = adOffsets(MINE_WXML);

    expect(adOffsets(MINE_WXML)).toHaveLength(2);
    expect(menuIdx).toBeGreaterThan(-1);
    // 绑定卡片与菜单卡片之间不放广告
    expect(MINE_WXML.indexOf('class="bind card"')).toBeLessThan(menuIdx);
    expect(menuIdx).toBeLessThan(upperAd);
    expect(MINE_WXML.slice(upperAd, lowerAd)).toContain('mineTop.unitId');
    expect(MINE_WXML.slice(lowerAd)).toContain('mineBottom.unitId');
  });

  test('WXML：两条广告各带 slot 标识、按各自的 error 隐藏', () => {
    expect(MINE_WXML.match(/data-slot="\{\{mine[A-Za-z]+\.slotKey\}\}"/g)).toHaveLength(2);
    expect(MINE_WXML.match(/binderror="onAdError"/g)).toHaveLength(2);
    expect(MINE_WXML).toContain('wx:if="{{!mineTop.adError}}"');
    expect(MINE_WXML).toContain('wx:if="{{!mineBottom.adError}}"');
  });
});
