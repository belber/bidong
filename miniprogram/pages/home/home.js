const { extractBiliLink } = require('../../utils/parse.js');
const { buildMockVideo } = require('../../utils/mock.js');

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
    // TODO: 后端就绪后改为调 api.parseVideo(link.url)，无效链接 toast 提示。
    // 当前为演示模式：不管输入内容都进入解析结果页，用 mock 数据展示。
    const video = buildMockVideo(link || {
      url: 'https://www.bilibili.com/video/BV1BE4U6BEg8'
    });
    getApp().globalData.pendingResult = video;
    wx.navigateTo({ url: '/pages/result/result' });
  }
});
