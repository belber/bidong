const api = require('../../utils/api.js');
const { buildMineAds } = require('../../utils/ads.js');

// 页面底部的两条横幅（上下叠放）：上面那条是原位置，下面那条是新加的
const [mineTop, mineBottom] = buildMineAds();

Page(Object.assign({
  data: {
    bound: false,
    biliUid: '',
    biliName: '',
    showRobotGuide: true,
    mineTop,
    mineBottom
  },

  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 2 });
    }
    this.loadUiConfig();
    this.refreshBinding();
  },

  loadUiConfig() {
    api
      .getPublicConfig()
      .then((cfg) => {
        this.setData({ showRobotGuide: cfg.robot_guide !== false });
      })
      .catch(() => {});
  },

  refreshBinding() {
    api
      .getBinding()
      .then((r) => {
        this.setData({
          bound: !!r.bound,
          biliUid: r.bili_uid || '',
          biliName: r.bili_name || ''
        });
      })
      .catch(() => {});
  },

  // 两条广告各自独立：只隐藏加载失败的那一条（slotKey 由 data-slot 带过来）
  onAdError(e) {
    const slotKey = (e && e.currentTarget && e.currentTarget.dataset
      ? e.currentTarget.dataset.slot
      : '') || '';
    console.warn('[ad] 我的页横幅加载失败', slotKey, e && e.detail);

    const patch = {};
    ['mineTop', 'mineBottom'].forEach((key) => {
      if (this.data[key] && this.data[key].slotKey === slotKey) {
        patch[key] = Object.assign({}, this.data[key], { adError: true });
      }
    });
    this.setData(patch);
  },

  onBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  onUnbind() {
    wx.showModal({
      title: '解绑',
      content: '解绑后 @壁咚咚私藏 将不再自动收藏到你的账号，确定解绑？',
      confirmText: '解绑',
      confirmColor: '#FB7299',
      success: (res) => {
        if (!res.confirm) {
          return;
        }
        api
          .unbind()
          .then(() => {
            this.setData({ bound: false, biliUid: '', biliName: '' });
            wx.showToast({ title: '已解绑', icon: 'success' });
          })
          .catch((err) => {
            wx.showToast({ title: err.message || '解绑失败', icon: 'none' });
          });
      }
    });
  },

  onGoHelp() {
    wx.navigateTo({ url: '/pages/help/help' });
  },

  onGoAbout() {
    wx.navigateTo({ url: '/pages/about/about' });
  },

  onGoPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  }
}, require("../../utils/share.js").pageShare));
