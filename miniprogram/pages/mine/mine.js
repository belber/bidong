const api = require('../../utils/api.js');

Page({
  data: {
    bound: false,
    biliUid: '',
    biliName: '',
    showRobotGuide: true
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

  onBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  onUnbind() {
    wx.showModal({
      title: '解绑',
      content: '解绑后 @壁咚收藏夹 将不再自动收藏到你的账号，确定解绑？',
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
});
