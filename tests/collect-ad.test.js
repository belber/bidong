// 广告位随视图走：列表每 5 张一条（插在卡片流里），网格每个月份分组末尾一条整行横幅。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');

let seq = 0;
function card(month) {
  seq += 1;
  return {
    id: seq,
    bvid: 'BV' + seq,
    title: '标题' + seq,
    month,
    collected_at: seq,
    duration: 61,
    cover_url: '/media/covers/BV' + seq + '.jpg',
    tags: [],
    partition: '知识',
    up_name: '某UP',
    source: 'local'
  };
}

function tap(dataset) {
  return { currentTarget: { dataset } };
}

function gridPage(cards) {
  const { ctx } = loadPage(COLLECT);
  ctx.setData({ isBound: true, view: 'grid', cards });
  ctx.rebuild();
  return ctx;
}

describe('收藏夹广告位', () => {
  test('网格：每个月份分组末尾一条整行广告，卡片流里不再掺广告', () => {
    const ctx = gridPage([card('2026-10'), card('2026-10'), card('2026-09')]);

    expect(ctx.data.groups).toHaveLength(2);
    ctx.data.groups.forEach((group) => {
      expect(group.items.some((it) => it.isAd)).toBe(false);
      expect(group.ad.isAd).toBe(true);
      expect(group.ad.adError).toBe(false);
    });
    const slots = ctx.data.groups.map((g) => g.ad.slotKey);
    expect(new Set(slots).size).toBe(slots.length);
  });

  test('列表：仍是每 5 张一条，插在卡片流里，没有分组级广告', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, view: 'list', cards: Array.from({ length: 6 }, () => card('2026-10')) });
    ctx.rebuild();

    const items = ctx.data.groups[0].items;
    expect(items.filter((it) => it.isAd)).toHaveLength(1);
    expect(items.map((it) => !!it.isAd)).toEqual([false, false, false, false, false, true, false]);
    expect(ctx.data.groups[0].ad).toBeFalsy();
  });

  test('切换视图会按新视图重算广告', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, view: 'list', cards: Array.from({ length: 6 }, () => card('2026-10')) });
    ctx.rebuild();
    expect(ctx.data.groups[0].items.some((it) => it.isAd)).toBe(true);

    ctx.onViewTap(tap({ view: 'grid' }));
    expect(ctx.data.groups[0].items.some((it) => it.isAd)).toBe(false);
    expect(ctx.data.groups[0].ad.isAd).toBe(true);

    ctx.onViewTap(tap({ view: 'list' }));
    expect(ctx.data.groups[0].items.some((it) => it.isAd)).toBe(true);
    expect(ctx.data.groups[0].ad).toBeFalsy();
  });

  test('网格广告加载失败：只隐藏出错的那个分组的广告', () => {
    const ctx = gridPage([card('2026-10'), card('2026-09')]);
    const [first, second] = ctx.data.groups;

    ctx.onAdError({ currentTarget: { dataset: { slot: first.ad.slotKey } } });

    expect(ctx.data.groups[0].ad.adError).toBe(true);
    expect(ctx.data.groups[1].ad.slotKey).toBe(second.ad.slotKey);
    expect(ctx.data.groups[1].ad.adError).toBe(false);
  });

  test('列表广告加载失败仍然只隐藏那一条', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, view: 'list', cards: Array.from({ length: 6 }, () => card('2026-10')) });
    ctx.rebuild();
    const ad = ctx.data.groups[0].items.find((it) => it.isAd);

    ctx.onAdError({ currentTarget: { dataset: { slot: ad.slotKey } } });

    expect(ctx.data.groups[0].items.filter((it) => it.isAd)[0].adError).toBe(true);
  });
});
