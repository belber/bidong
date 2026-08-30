const { validateActivationCode } = require('../../utils/bind.js');

Page({
  data: {
    code: ''
  },

  onInput(e) {
    this.setData({ code: e.detail.value });
  },

  onPaste() {
    wx.getClipboardData({
      success: (res) => {
        this.setData({ code: (res.data || '').trim() });
      }
    });
  },

  onBind() {
    const result = validateActivationCode(this.data.code);
    if (!result.valid) {
      wx.showToast({ title: '请输入有效激活码', icon: 'none' });
      return;
    }

    // TODO: 后端就绪后调用 POST /api/binding { activation_code: result.code }
    // 当前为演示：直接提示成功并返回「我的」页。
    wx.showToast({ title: '绑定成功', icon: 'success' });
    setTimeout(() => wx.navigateBack(), 600);
  }
});
