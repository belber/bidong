const { groupByMonth } = require('../../utils/group.js');
const { filterCards } = require('../../utils/filter.js');
const { formatDuration } = require('../../utils/format.js');
const api = require('../../utils/api.js');

Page({
  data: {
    cards: [],
    sourceFilter: 'all',
    keyword: '',
    partitionFilter: '全部',
    allPartitions: ['全部'],
    groups: [],
    isBound: false,
    hasRobotRecords: false,
    showRobotGuide: false,
    editing: false,
    selectedCount: 0
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
          dur: formatDuration(c.duration),
          selected: false
        }));
        this.setData({ cards: mapped, editing: false }, () => this.rebuild());
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败', icon: 'none' });
      });
  },

  rebuild() {
    const filtered = filterCards(this.data.cards, {
      source: this.data.sourceFilter,
      partition: this.data.partitionFilter,
      keyword: this.data.keyword
    });

    const partitions = ['全部'];
    this.data.cards.forEach((c) => {
      if (c.partition && !partitions.includes(c.partition)) {
        partitions.push(c.partition);
      }
    });

    const hasRobotRecords = this.data.cards.some((c) => c.source === 'robot');
    const showRobotGuide =
      this.data.sourceFilter === 'robot' &&
      (!this.data.isBound || !hasRobotRecords);
    const selectedCount = filtered.filter((c) => c.selected).length;

    this.setData({
      groups: groupByMonth(filtered),
      allPartitions: partitions,
      hasRobotRecords,
      showRobotGuide,
      selectedCount
    });
  },

  onSourceTap(e) {
    this.setData({ sourceFilter: e.currentTarget.dataset.source }, () => this.rebuild());
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

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => String(c.id) === String(id));
    if (!card) {
      return;
    }
    if (this.data.editing) {
      this.toggleSelect(id);
      return;
    }
    wx.navigateTo({ url: '/pages/result/result?bvid=' + card.bvid });
  },

  onCardLongPress(e) {
    if (this.data.editing) {
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
});
