const { extractBiliLink } = require('../../utils/parse.js');
const api = require('../../utils/api.js');

Page({
  data: {
    input: ''
  },

  onShow() {
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 0 });
    }
  },

  onPaste() {
    wx.getClipboardData({
      success: (res) => {
        const text = (res.data || '').trim();
        const link = extractBiliLink(text);
        if (!link) {
          wx.showToast({ title: '剪贴板里没有 B站视频链接', icon: 'none' });
          return;
        }
        this.setData({ input: text });
      }
    });
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  onParse() {
    const link = extractBiliLink(this.data.input);
    if (!link) {
      wx.showToast({ title: '请输入 B站视频链接或 BV 号', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '解析中' });
    api.parse(link.url)
      .then((card) => {
        wx.hideLoading();
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        wx.navigateTo({ url: '/pages/result/result' });
      })
      .catch((err) => {
        wx.hideLoading();
        wx.showToast({ title: err.message || '解析失败', icon: 'none' });
      });
  }
});
