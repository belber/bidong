// 广告位配置：unit-id 收敛于此，换位/下线只改这一处。
// 详见 docs/ads-plan.md
module.exports = {
  HOME_BANNER: 'adunit-2b1d1372956d1cf1',
  COLLECT_FEED: 'adunit-c956d609cf9f653b',
  RESULT_BANNER: 'adunit-f522117f9e3fd28b',
  // 我的页底部放两条横幅，上下叠放：先旧位（上，mine-top）后新位（下，mine-bottom）。
  // 两条各自独立的广告位：流量主后台的曝光/点击按广告位聚合，共用就分不清
  // 是上面那条还是下面那条在出量。配置只用 unit-id 区分，页面代码两条完全一样。
  // 上条沿用原「我的页底部」广告位，历史数据不断档；下条是 2026-10-15 新建的。
  MINE_BANNER_TOP: 'adunit-0eb305e833051a6a',
  MINE_BANNER_BOTTOM: 'adunit-0e7a81112e9dcd7a'
};
