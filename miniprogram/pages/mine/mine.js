Page({
  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 2 });
    }
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
