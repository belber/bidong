Component({
  data: {
    statusBarHeight: 20
  },

  lifetimes: {
    attached() {
      let height = 20;
      try {
        height = wx.getWindowInfo().statusBarHeight || 20;
      } catch (e) {
        try {
          height = wx.getSystemInfoSync().statusBarHeight || 20;
        } catch (err) {
          // 保底默认
        }
      }
      this.setData({ statusBarHeight: height });
    }
  }
});
