Page({
  data: {
    groupNo: '',
    showGroup: false
  },

  onLoad() {
    const api = require('../../utils/api');
    api
      .getHelpConfig()
      .then((cfg) => {
        const no = ((cfg && cfg.qq_group) || '').trim();
        this.setData({ groupNo: no, showGroup: !!no });
      })
      .catch(() => this.setData({ showGroup: false }));
  },

  onCopyGroup() {
    wx.setClipboardData({
      data: this.data.groupNo,
      success: () => wx.showToast({ title: '群号已复制，去 QQ 搜索加入', icon: 'none' })
    });
  }
});
