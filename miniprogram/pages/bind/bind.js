const api = require('../../utils/api.js');
const { validateActivationCode } = require('../../utils/bind.js');

function toast(title) {
  wx.showToast({ title, icon: 'none' });
}

Page({
  data: {
    code: '',
    loading: false,
    bound: false,
    biliUid: ''
  },

  onShow() {
    this.refreshStatus();
  },

  refreshStatus() {
    api
      .getBinding()
      .then((r) => {
        this.setData({ bound: !!r.bound, biliUid: r.bili_uid || '' });
      })
      .catch(() => {});
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
    if (this.data.loading || this.data.bound) {
      return;
    }
    const result = validateActivationCode(this.data.code);
    if (!result.valid) {
      toast('请输入有效激活码');
      return;
    }
    this.setData({ loading: true });
    api
      .bind(result.code)
      .then((r) => {
        this.setData({ bound: true, biliUid: r.bili_uid || '' });
        wx.showToast({ title: '绑定成功', icon: 'success' });
        setTimeout(() => wx.navigateBack(), 900);
      })
      .catch((err) => {
        this.setData({ loading: false });
        toast(err.message || '绑定失败，请检查激活码');
      });
  }
});
