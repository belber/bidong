const { formatDuration, formatDateTime } = require('../../utils/format.js');

Page({
  data: {
    video: {
      title: '',
      up_name: '',
      partition: '',
      tags: [],
      desc: '',
      subtitles: []
    },
    dur: '00:00',
    pubText: '',
    upInitial: ''
  },

  onLoad() {
    const video = getApp().globalData.pendingResult;
    if (!video) {
      wx.showToast({ title: '暂无解析数据', icon: 'none' });
      return;
    }

    const subtitles = (video.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));

    this.setData({
      video: Object.assign({}, video, { subtitles }),
      dur: formatDuration(video.duration),
      pubText: formatDateTime(video.pubdate),
      upInitial: (video.up_name || '?').slice(0, 1)
    });
  },

  onOpenBili() {
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      wx.showToast({ title: 'B站小程序 appId 尚未配置', icon: 'none' });
      return;
    }
    wx.navigateToMiniProgram({
      appId,
      path: '/pages/video/video?bvid=' + this.data.video.bvid
    });
  },

  onMoreSub() {
    // TODO: 后端字幕接口就绪后加载完整字幕
    wx.showToast({ title: '完整字幕将在后端接入后提供', icon: 'none' });
  },

  onDownloadSub() {
    // TODO: 下载字幕（后端返回 subtitle_url 后调用下载）
    wx.showToast({ title: '字幕下载将在后端接入后提供', icon: 'none' });
  }
});
