Component({
  data: {
    selected: 0,
    list: [
      { pagePath: '/pages/home/home', text: '贴链接', icon: 'link' },
      { pagePath: '/pages/collect/collect', text: '收藏夹', icon: 'fav' },
      { pagePath: '/pages/mine/mine', text: '我的', icon: 'me' }
    ]
  },

  methods: {
    switchTab(e) {
      wx.switchTab({
        url: this.data.list[e.currentTarget.dataset.index].pagePath
      });
    }
  }
});
