const ADS_CONFIG = require('../config/ads.js');
const { COLLECT_FEED } = ADS_CONFIG;

// 收藏夹信息流广告：每 5 张卡片后插 1 条（跨月份分组按全局序号计算）。
// 收藏不足 5 张时，在列表末尾补 1 条，避免低频用户完全看不到广告。
const COLLECT_FEED_INTERVAL = 5;

/**
 * 创建一个独立信息流广告条目，主要用于收藏夹空态。
 * 广告条目形如 { isAd: true, unitId, slotKey, adError }，
 * 渲染时用 wx:if 分支展示 <ad>，加载失败把 adError 置 true 即隐藏容器。
 */
function buildFeedAd(slotKey) {
  return {
    isAd: true,
    id: 'ad-' + slotKey,
    unitId: COLLECT_FEED,
    slotKey: slotKey,
    adError: false
  };
}

function buildFeedGroups(groups, interval) {
  const step = interval || COLLECT_FEED_INTERVAL;
  let cardCount = 0;
  let adCount = 0;

  const result = groups.map((group) => {
    const items = [];
    group.items.forEach((card) => {
      items.push(card);
      cardCount += 1;
      if (cardCount % step === 0) {
        items.push(buildFeedAd('feed-' + adCount));
        adCount += 1;
      }
    });
    return Object.assign({}, group, { items });
  });

  if (cardCount > 0 && cardCount < step) {
    result[result.length - 1].items.push(buildFeedAd('feed-' + adCount));
    adCount += 1;
  }

  return result;
}

// 网格视图的广告位：每个月份分组末尾挂一条整行横幅。
// 挂在分组边界上而不是塞进网格，整行天然成立——塞进网格的话，月份内卡片数是奇数时
// 会在最后一行空出半格。slotKey 带上月份，出错时能直接定位到是哪个分组的广告。
function buildMonthAdGroups(groups) {
  return groups.map((group) =>
    Object.assign({}, group, { ad: buildFeedAd("feed-" + group.month) })
  );
}

// 我的页底部的两条横幅：贴在菜单卡片下方的留白里，上下叠放，
// 先旧位（mine-top）后新位（mine-bottom）。该页没有列表内容、留白超过半屏，
// 单条横幅填不满所以放两条；出错时按 slotKey 只隐藏出错的那一条，另一条照常展示。
function buildMineAds() {
  return [
    { slotKey: 'mine-top', unitId: ADS_CONFIG.MINE_BANNER_TOP },
    { slotKey: 'mine-bottom', unitId: ADS_CONFIG.MINE_BANNER_BOTTOM }
  ].map((slot) => Object.assign({ id: 'ad-' + slot.slotKey, adError: false }, slot));
}

const AD_UNIT_IDS = {
  homeBanner: ADS_CONFIG.HOME_BANNER,
  collectFeed: ADS_CONFIG.COLLECT_FEED,
  resultBanner: ADS_CONFIG.RESULT_BANNER,
  mineBannerTop: ADS_CONFIG.MINE_BANNER_TOP,
  mineBannerBottom: ADS_CONFIG.MINE_BANNER_BOTTOM
};

module.exports = {
  buildFeedGroups,
  buildMonthAdGroups,
  buildFeedAd,
  buildMineAds,
  COLLECT_FEED_INTERVAL,
  AD_UNIT_IDS
};
