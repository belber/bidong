const {
  buildFeedGroups,
  buildMonthAdGroups,
  buildFeedAd,
  buildMineAds,
  COLLECT_FEED_INTERVAL,
  AD_UNIT_IDS
} = require('./ads');

function makeGroups(sizes) {
  let id = 0;
  return sizes.map((n, gi) => ({
    month: `2026-0${gi + 1}`,
    count: n,
    items: Array.from({ length: n }, () => ({ id: ++id, title: `card-${id}` }))
  }));
}

function flatten(groups) {
  return groups.reduce((acc, g) => acc.concat(g.items), []);
}

function adIndexes(groups) {
  return flatten(groups)
    .map((it, i) => (it.isAd ? i : -1))
    .filter((i) => i >= 0);
}

describe('collect feed ad slots', () => {
  test('exposes unit ids and 5-card feed interval', () => {
    expect(AD_UNIT_IDS.homeBanner).toBe('adunit-2b1d1372956d1cf1');
    expect(AD_UNIT_IDS.collectFeed).toBe('adunit-c956d609cf9f653b');
    expect(AD_UNIT_IDS.resultBanner).toBe('adunit-f522117f9e3fd28b');
    // 两条横幅都在我的页底部上下叠放：上面那条沿用原「我的页底部」广告位，
    // 下面那条是新建的；曝光/点击按广告位分开统计。
    expect(AD_UNIT_IDS.mineBannerTop).toBe('adunit-0eb305e833051a6a');
    expect(AD_UNIT_IDS.mineBannerBottom).toBe('adunit-0e7a81112e9dcd7a');
    expect(COLLECT_FEED_INTERVAL).toBe(5);
  });

  test('我的页两条横幅位：slotKey 与 unit-id 各自独立', () => {
    const slots = buildMineAds();

    expect(slots.map((s) => s.slotKey)).toEqual(['mine-top', 'mine-bottom']);
    expect(slots.map((s) => s.unitId)).toEqual([
      AD_UNIT_IDS.mineBannerTop,
      AD_UNIT_IDS.mineBannerBottom
    ]);
    slots.forEach((s) => expect(s.adError).toBe(false));
  });

  test('我的页两条广告位互不影响：slotKey 与 unit-id 都各是各的', () => {
    const slots = buildMineAds();
    const keys = slots.map((s) => s.slotKey);
    const units = slots.map((s) => s.unitId);

    expect(new Set(keys).size).toBe(keys.length);
    // 分开建广告位：报表才分得清是哪个位置在出量
    expect(new Set(units).size).toBe(units.length);
  });

  test('creates an ad for the empty collection state', () => {
    expect(buildFeedGroups([], COLLECT_FEED_INTERVAL)).toEqual([]);
    const ad = buildFeedAd('feed-empty');
    expect(ad.isAd).toBe(true);
    expect(ad.unitId).toBe('adunit-c956d609cf9f653b');
    expect(ad.slotKey).toBe('feed-empty');
    expect(ad.adError).toBe(false);
  });

  test('shows at least one ad for fewer than five cards', () => {
    for (const size of [1, 2, 4]) {
      const flat = flatten(buildFeedGroups(makeGroups([size]), COLLECT_FEED_INTERVAL));
      expect(adIndexes(buildFeedGroups(makeGroups([size]), COLLECT_FEED_INTERVAL))).toEqual([flat.length - 1]);
    }
  });

  test('inserts the first ad after five cards without an extra trailing ad', () => {
    const flat = flatten(buildFeedGroups(makeGroups([6]), COLLECT_FEED_INTERVAL));
    expect(adIndexes(buildFeedGroups(makeGroups([6]), COLLECT_FEED_INTERVAL))).toEqual([5]);
    expect(flat).toHaveLength(7);
  });

  test('inserts ads every five cards across month boundaries', () => {
    const groups = buildFeedGroups(makeGroups([6, 6]), COLLECT_FEED_INTERVAL);
    expect(adIndexes(groups)).toEqual([5, 11]);
  });

  test('inserts multiple ads with correct spacing', () => {
    const groups = buildFeedGroups(makeGroups([9, 9, 9]), COLLECT_FEED_INTERVAL);
    expect(adIndexes(groups)).toEqual([5, 11, 17, 23, 29]);
  });

  test('ad entries carry unit id and slot key', () => {
    const groups = buildFeedGroups(makeGroups([9]), COLLECT_FEED_INTERVAL);
    const ad = flatten(groups).find((it) => it.isAd);
    expect(ad.unitId).toBe('adunit-c956d609cf9f653b');
    expect(ad.slotKey).toBe('feed-0');
    expect(ad.adError).toBe(false);
  });
});

describe('网格视图的按月广告位', () => {
  test('每个月份分组末尾各挂一条，卡片列表里不再掺广告', () => {
    const groups = buildMonthAdGroups(makeGroups([6, 2, 9]));

    expect(groups).toHaveLength(3);
    groups.forEach((g) => {
      expect(g.items.some((it) => it.isAd)).toBe(false);
      expect(g.ad.isAd).toBe(true);
      expect(g.ad.unitId).toBe('adunit-c956d609cf9f653b');
      expect(g.ad.adError).toBe(false);
    });
  });

  test('月份卡片数量少也照样挂一条（分组末尾一条，不按月内张数算）', () => {
    const groups = buildMonthAdGroups(makeGroups([1, 1]));
    expect(groups.map((g) => !!g.ad)).toEqual([true, true]);
  });

  test('slotKey 按月份区分，便于定位是哪个分组的广告出错', () => {
    const groups = buildMonthAdGroups(makeGroups([3, 3]));
    expect(groups.map((g) => g.ad.slotKey)).toEqual(['feed-2026-01', 'feed-2026-02']);
  });

  test('保留分组原本的字段与卡片顺序', () => {
    const source = makeGroups([2]);
    const groups = buildMonthAdGroups(source);
    expect(groups[0].month).toBe('2026-01');
    expect(groups[0].count).toBe(2);
    expect(groups[0].items.map((it) => it.id)).toEqual([1, 2]);
  });

  test('没有分组时返回空数组', () => {
    expect(buildMonthAdGroups([])).toEqual([]);
  });
});
