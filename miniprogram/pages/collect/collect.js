const { groupByMonth } = require('../../utils/group.js');
const { filterCards } = require('../../utils/filter.js');
const { formatDuration } = require('../../utils/format.js');
const api = require('../../utils/api.js');

Page({
  data: {
    cards: [],
    sourceFilter: 'all',
    tagFilter: '全部',
    allTags: ['全部'],
    groups: [],
    // TODO: 后端就绪后从接口读取用户绑定状态
    isBound: false,
    hasRobotRecords: false,
    showRobotGuide: false
  },

  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 1 });
    }
    this.loadCards();
  },

  onPullDownRefresh() {
    this.loadCards();
    wx.stopPullDownRefresh();
  },

  loadCards() {
    api.getCards()
      .then((cards) => {
        const mapped = cards.map((c) => Object.assign({}, c, {
          dur: formatDuration(c.duration)
        }));
        this.setData({ cards: mapped }, () => this.rebuild());
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败', icon: 'none' });
      });
  },

  rebuild() {
    const filtered = filterCards(this.data.cards, {
      source: this.data.sourceFilter,
      tag: this.data.tagFilter
    });

    const tags = ['全部'];
    this.data.cards.forEach((c) => {
      (c.tags || []).forEach((t) => {
        if (!tags.includes(t)) {
          tags.push(t);
        }
      });
    });

    const hasRobotRecords = this.data.cards.some((c) => c.source === 'robot');
    const showRobotGuide =
      this.data.sourceFilter === 'robot' &&
      (!this.data.isBound || !hasRobotRecords);

    this.setData({
      groups: groupByMonth(filtered),
      allTags: tags,
      hasRobotRecords,
      showRobotGuide
    });
  },

  onSourceTap(e) {
    this.setData({ sourceFilter: e.currentTarget.dataset.source }, () => this.rebuild());
  },

  onTagTap(e) {
    this.setData({ tagFilter: e.currentTarget.dataset.tag }, () => this.rebuild());
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => String(c.id) === String(id));
    if (!card) {
      return;
    }
    wx.navigateTo({ url: '/pages/result/result?bvid=' + card.bvid });
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '删除收藏',
      content: '删除后不可恢复，确定删除？',
      success: (res) => {
        if (!res.confirm) {
          return;
        }
        api.deleteCard(id)
          .then(() => {
            wx.showToast({ title: '已删除', icon: 'success' });
            this.loadCards();
          })
          .catch((err) => {
            wx.showToast({ title: err.message || '删除失败', icon: 'none' });
          });
      }
    });
  },

  onGotoParse() {
    wx.switchTab({ url: '/pages/home/home' });
  }
});
