const { extractBiliLink } = require('../../utils/parse.js');
const api = require('../../utils/api.js');

Page({
  data: {
    input: '',
    parsing: false
  },

  onShow() {
    if (this.data.parsing) {
      this.setData({ parsing: false });
    }
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
    if (this.data.parsing) {
      return;
    }
    const link = extractBiliLink(this.data.input);
    if (!link) {
      wx.showToast({ title: '请输入 B站视频链接或 BV 号', icon: 'none' });
      return;
    }
    this.setData({ parsing: true });
    const minWait = new Promise((resolve) => setTimeout(resolve, 700));
    const parseReq = api.parse(link.url);
    Promise.all([parseReq, minWait])
      .then(([card]) => {
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        wx.navigateTo({ url: '/pages/result/result' });
      })
      .catch((err) => {
        this.setData({ parsing: false });
        wx.showToast({ title: err.message || '解析失败', icon: 'none' });
      });
  }
});
