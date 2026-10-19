// 我的页只保留一条底部横幅（mine-top），出错时隐藏容器。
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

describe('我的页底部广告位', () => {
  test('页面数据里只准备一条广告位', () => {
    const { ctx } = loadPage(MINE_JS);

    expect(ctx.data.mineTop.slotKey).toBe('mine-top');
    // 页面只读 config，不写死 id：换广告位只改 config/ads.js
    expect(ctx.data.mineTop.unitId).toBe(ADS.MINE_BANNER_TOP);
    expect(ctx.data.mineTop.adError).toBe(false);
    expect(ctx.data.mineBottom).toBeUndefined();
  });

  test('加载失败时隐藏广告容器', () => {
    const { ctx } = loadPage(MINE_JS);

    ctx.onAdError(adFail('mine-top'));

    expect(ctx.data.mineTop.adError).toBe(true);
  });

  test('WXML：只渲染一条横幅，并排在菜单卡片下方', () => {
    const menuIdx = MINE_WXML.indexOf('class="menu card"');
    const [adOffset] = adOffsets(MINE_WXML);

    expect(adOffsets(MINE_WXML)).toHaveLength(1);
    expect(menuIdx).toBeGreaterThan(-1);
    // 绑定卡片与菜单卡片之间不放广告
    expect(MINE_WXML.indexOf('class="bind card"')).toBeLessThan(menuIdx);
    expect(menuIdx).toBeLessThan(adOffset);
    expect(MINE_WXML.slice(adOffset)).toContain('mineTop.unitId');
    expect(MINE_WXML).not.toContain('mineBottom');
  });

  test('WXML：广告带 slot 标识并按 error 隐藏', () => {
    expect(MINE_WXML.match(/data-slot="\{\{mine[A-Za-z]+\.slotKey\}\}"/g)).toHaveLength(1);
    expect(MINE_WXML.match(/binderror="onAdError"/g)).toHaveLength(1);
    expect(MINE_WXML).toContain('wx:if="{{!mineTop.adError}}"');
  });
});
