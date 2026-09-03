const api = require('../../utils/api.js');

Page({
  data: {
    bound: false,
    biliUid: ''
  },

  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 2 });
    }
    this.refreshBinding();
  },

  refreshBinding() {
    api
      .getBinding()
      .then((r) => {
        this.setData({ bound: !!r.bound, biliUid: r.bili_uid || '' });
      })
      .catch(() => {});
  },

  onBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
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
});
