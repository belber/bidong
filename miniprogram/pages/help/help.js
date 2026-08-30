Page({
  data: {
    // TODO: 上线前改为后端下发群号（群满/解散可更换）
    groupNo: '123456789'
  },

  onCopyGroup() {
    wx.setClipboardData({
      data: this.data.groupNo,
      success: () => {
        wx.showToast({ title: '群号已复制，去 QQ 搜索加入', icon: 'none' });
      }
    });
  }
});
