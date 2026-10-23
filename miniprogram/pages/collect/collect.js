const { groupByMonth } = require('../../utils/group.js');
const { filterCards, DOUYIN } = require('../../utils/filter.js');
const { formatDuration } = require('../../utils/format.js');
const {
  DEFAULT_VIEW,
  DEFAULT_COLS,
  normalizeView,
  readPrefs,
  savePrefs,
  hasSeenPinchHint,
  markPinchHintSeen
} = require('../../utils/viewPref.js');
const { pinchDistance, createPinchTracker } = require('../../utils/pinchZoom.js');
const { nextViewForSwipe } = require('../../utils/swipeView.js');
const api = require('../../utils/api.js');
const { buildFeedGroups, buildMonthAdGroups, buildFeedAd } = require('../../utils/ads.js');

// 捏合/横滑收尾时系统可能补一个 tap，这段时间内吞掉卡片点按，避免误跳 B站
const TAP_GUARD_MS = 400;

Page(Object.assign({
  data: {
    cards: [],
    keyword: '',
    partitionFilter: '全部',
    allPartitions: ['全部'],
    groups: [],
    isBound: false,
    showRobotGuide: false,
    view: DEFAULT_VIEW,
    cols: DEFAULT_COLS,
    editing: false,
    selectedCount: 0,
    refreshing: false,
    emptyAd: buildFeedAd('feed-empty')
  },

  onLoad() {
    // 视图偏好只在这里读一次：页面内切换时 data 已经是新的，不需要回读缓存。
    const prefs = readPrefs();
    this.setData({ view: prefs.view, cols: prefs.cols });
    this.maybeShowPinchHint();
  },

  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 1 });
    }
    this.loadCards();
  },

  onRefresh() {
    this.setData({ refreshing: true });
    this.loadCards(() => this.setData({ refreshing: false }));
  },

  loadCards(done) {
    Promise.all([
      api.getCards(),
      api.getBinding().catch(() => ({ bound: false }))
    ])
      .then(([cards, binding]) => {
        const mapped = cards.map((c) => Object.assign({}, c, {
          dur: formatDuration(c.duration),
          // 本地存储后端给的是相对路径，这里补成当前环境的绝对地址；COS 绝对地址原样透传
          cover_url: api.resolveMediaUrl(c.cover_url),
          selected: false
        }));
        this.setData({
          cards: mapped,
          isBound: !!binding.bound,
          editing: false
        }, () => this.rebuild());
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败', icon: 'none' });
      })
      .finally(() => {
        if (typeof done === 'function') done();
      });
  },

  rebuild() {
    const filtered = filterCards(this.data.cards, {
      partition: this.data.partitionFilter,
      keyword: this.data.keyword
    });

    const partitions = ['全部'];
    // 抖音作品没有分区，单独给一个入口；没有抖音卡片时这一项不出现
    if (this.data.cards.some((c) => (c.platform || 'bilibili') === 'douyin')) {
      partitions.push(DOUYIN);
    }
    this.data.cards.forEach((c) => {
      if (c.partition && !partitions.includes(c.partition)) {
        partitions.push(c.partition);
      }
    });

    // 引导卡原来挂在「@壁咚咚」来源分页上；分页去掉后改挂在「未绑定 + 收藏夹还空着」上，
    // 也就是它真正有用的那一次：新用户第一次进来不知道怎么用。
    const showRobotGuide = !this.data.isBound && this.data.cards.length === 0;
    const selectedCount = filtered.filter((c) => c.selected).length;

    // 广告位随视图走：列表每 5 张一条插在卡片流里，网格每个月份分组末尾一条整行横幅
    const grouped = groupByMonth(filtered);
    const groups =
      this.data.view === 'grid' ? buildMonthAdGroups(grouped) : buildFeedGroups(grouped);

    this.setData({
      groups,
      allPartitions: partitions,
      showRobotGuide,
      selectedCount
    });
  },

  onViewTap(e) {
    this.applyView(normalizeView(e.currentTarget.dataset.view));
  },

  // 按钮和左右滑动走同一条路径：改数据 + 落缓存 + 重算广告 + 首次提示
  applyView(view) {
    if (view === this.data.view) {
      return;
    }
    this.setData({ view });
    savePrefs({ view, cols: this.data.cols });
    this.rebuild(); // 两种视图的广告位规则不同，切视图要重算分组
    this.maybeShowPinchHint();
  },

  guardTap() {
    this.tapGuardUntil = Date.now() + TAP_GUARD_MS;
  },

  // 捏合没有按钮可点，只能提示一次让用户知道它存在
  maybeShowPinchHint() {
    if (this.data.view !== 'grid' || hasSeenPinchHint()) {
      return;
    }
    markPinchHintSeen();
    wx.showToast({ title: '双指捏合可调整列数', icon: 'none', duration: 2200 });
  },

  // 信息流手势区：双指捏合换列数、单指横滑换视图。
  // 用 bind（不是 catch），纵向滚动与下拉刷新照旧；单指手势只在横向明显压过纵向时才接管。
  onFeedTouchStart(e) {
    const touches = e.touches || [];
    this.pinch = null;
    this.pinchActive = false;
    this.swipe = null;

    if (this.data.editing || this.data.showRobotGuide) {
      return; // 编辑态/引导态不接管手势：那会儿没有视图切换入口，捏合也没意义
    }
    if (touches.length >= 2) {
      if (this.data.view !== 'grid') {
        return; // 列数只在网格视图里有意义
      }
      this.pinch = createPinchTracker(this.data.cols);
      this.pinch.begin(pinchDistance(touches));
      this.pinchActive = true;
      return;
    }
    if (touches.length === 1) {
      // 单指先记起点，抬手指时再判定要不要换视图（手指还按着就来回切会很晕）
      this.swipe = { x: touches[0].clientX, y: touches[0].clientY, dx: 0, dy: 0 };
    }
  },

  onFeedTouchMove(e) {
    const touches = e.touches || [];
    if (this.pinch) {
      if (touches.length < 2) {
        return;
      }
      const cols = this.pinch.update(pinchDistance(touches));
      if (cols !== this.data.cols) {
        this.setData({ cols }); // 实时重排，手感对齐系统相册
      }
      return;
    }
    if (!this.swipe || touches.length !== 1) {
      return;
    }
    const dx = touches[0].clientX - this.swipe.x;
    const dy = touches[0].clientY - this.swipe.y;
    // 记两个方向上各自的最远点：手指来回抖一下不该丢掉这次滑动，也不该把纵向滚动误判成横滑
    if (Math.abs(dx) > Math.abs(this.swipe.dx)) {
      this.swipe.dx = dx;
    }
    if (Math.abs(dy) > Math.abs(this.swipe.dy)) {
      this.swipe.dy = dy;
    }
  },

  onFeedTouchEnd(e) {
    const remaining = (e.touches || []).length;
    if (this.pinch) {
      if (remaining > 0) {
        return; // 还有手指没抬起来，手势没结束
      }
      this.pinch = null;
      this.pinchActive = false;
      this.guardTap();
      savePrefs({ view: this.data.view, cols: this.data.cols }); // 一次手势只写一次缓存
    }
    if (!this.swipe) {
      return;
    }
    const swipe = this.swipe;
    this.swipe = null;
    const next = nextViewForSwipe({ dx: swipe.dx, dy: swipe.dy, view: this.data.view });
    if (!next) {
      return;
    }
    this.guardTap(); // 滑动收尾时系统可能补一个 tap，别把用户带去 B站
    this.applyView(next);
  },

  onPartitionTap(e) {
    this.setData({ partitionFilter: e.currentTarget.dataset.partition }, () => this.rebuild());
  },

  onKeywordInput(e) {
    this.setData({ keyword: e.detail.value }, () => this.rebuild());
  },

  onClearKeyword() {
    this.setData({ keyword: '' }, () => this.rebuild());
  },

  visibleIds() {
    return this.data.groups.reduce((acc, g) => acc.concat(g.items.map((c) => String(c.id))), []);
  },

  onAdError(e) {
    console.warn('[ad] 收藏夹信息流加载失败', e && e.detail);
    const slotKey = e && e.currentTarget && e.currentTarget.dataset.slot;
    if (!slotKey) return;
    if (this.data.emptyAd && this.data.emptyAd.slotKey === slotKey) {
      this.setData({ emptyAd: Object.assign({}, this.data.emptyAd, { adError: true }) });
      return;
    }
    const groups = this.data.groups.map((g) => {
      const next = Object.assign({}, g, {
        items: g.items.map((it) => (it.isAd && it.slotKey === slotKey ? Object.assign({}, it, { adError: true }) : it))
      });
      // 网格视图的广告挂在分组上（不在 items 里）
      if (next.ad && next.ad.slotKey === slotKey) {
        next.ad = Object.assign({}, next.ad, { adError: true });
      }
      return next;
    });
    this.setData({ groups });
  },

  onCardTap(e) {
    // 捏合/横滑期间与收尾时系统可能补一个 tap，别让手指落点把用户带去 B站
    if (this.pinchActive || Date.now() < (this.tapGuardUntil || 0)) {
      return;
    }
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => String(c.id) === String(id));
    if (!card) {
      return;
    }
    if (this.data.editing) {
      this.toggleSelect(id);
      return;
    }
    // 抖音卡片必须带上平台，否则结果页会按 B站 拼出 bilibili.com/video/<抖音id>
    const platform = card.platform === 'douyin' ? 'douyin' : 'bilibili';
    wx.navigateTo({
      url: platform === 'douyin'
        ? '/pages/result/result?platform=douyin&id=' + card.bvid
        : '/pages/result/result?bvid=' + card.bvid
    });
  },

  onCardLongPress(e) {
    if (this.pinchActive || this.data.editing) {
      return;
    }
    const id = e.currentTarget.dataset.id;
    const cards = this.data.cards.map((c) => Object.assign({}, c, {
      selected: String(c.id) === String(id)
    }));
    this.setData({ editing: true, cards }, () => this.rebuild());
  },

  toggleSelect(id) {
    const cards = this.data.cards.map((c) => {
      if (String(c.id) === String(id)) {
        return Object.assign({}, c, { selected: !c.selected });
      }
      return c;
    });
    this.setData({ cards }, () => this.rebuild());
  },

  onSelectAll() {
    const vis = this.visibleIds();
    const cards = this.data.cards.map((c) => {
      if (vis.indexOf(String(c.id)) >= 0) {
        return Object.assign({}, c, { selected: true });
      }
      return c;
    });
    this.setData({ cards }, () => this.rebuild());
  },

  onCancelEdit() {
    const cards = this.data.cards.map((c) => Object.assign({}, c, { selected: false }));
    this.setData({ editing: false, cards }, () => this.rebuild());
  },

  onDeleteSelected() {
    const ids = this.data.cards.filter((c) => c.selected).map((c) => c.id);
    if (!ids.length) {
      return;
    }
    wx.showModal({
      title: '删除收藏',
      content: '删除 ' + ids.length + ' 个视频，删除后不可恢复，确定删除？',
      success: (res) => {
        if (!res.confirm) {
          return;
        }
        wx.showLoading({ title: '删除中' });
        Promise.all(ids.map((id) => api.deleteCard(id)))
          .then(() => {
            wx.hideLoading();
            wx.showToast({ title: '已删除', icon: 'success' });
            this.setData({ editing: false });
            this.loadCards();
          })
          .catch((err) => {
            wx.hideLoading();
            wx.showToast({ title: err.message || '删除失败', icon: 'none' });
          });
      }
    });
  },

  onGotoParse() {
    wx.switchTab({ url: '/pages/home/home' });
  }
}, require("../../utils/share.js").pageShare));
