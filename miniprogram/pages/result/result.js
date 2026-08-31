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
    upInitial: '',
    subPreview: [],
    showAllSub: false
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
      subPreview: subtitles.slice(0, 5),
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

  copyText(text) {
    if (!text) {
      wx.showToast({ title: '没有可复制的内容', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: text,
      success() {
        wx.showToast({ title: '已复制', icon: 'success' });
      }
    });
  },

  onPreviewCover() {
    const url = this.data.video.cover_url;
    if (!url) {
      return;
    }
    wx.previewImage({ urls: [url] });
  },

  onToggleSub() {
    this.setData({ showAllSub: !this.data.showAllSub });
  },

  onCopyTitle() {
    this.copyText(this.data.video.title);
  },

  onCopyTags() {
    this.copyText((this.data.video.tags || []).map((t) => '#' + t).join(' '));
  },

  onCopyDesc() {
    this.copyText(this.data.video.desc);
  },

  onCopyLink() {
    this.copyText(this.data.video.source_url || this.data.video.bvid);
  },

  onCopySub() {
    const lines = (this.data.video.subtitles || []).map((s) => s.timeText + ' ' + s.text);
    this.copyText(lines.join('\n'));
  },

  onCopyAll() {
    const v = this.data.video;
    const lines = [];
    if (v.title) {
      lines.push('标题：' + v.title);
    }
    const meta = [v.up_name, v.partition, v.bvid].filter(Boolean).join(' · ');
    if (meta) {
      lines.push('来源：' + meta);
    }
    if (v.source_url) {
      lines.push('链接：' + v.source_url);
    }
    if ((v.tags || []).length) {
      lines.push('标签：' + (v.tags || []).map((t) => '#' + t).join(' '));
    }
    if (v.desc) {
      lines.push('简介：' + v.desc);
    }
    if ((v.subtitles || []).length) {
      lines.push('字幕：');
      (v.subtitles || []).forEach((s) => lines.push(s.timeText + ' ' + s.text));
    }
    this.copyText(lines.join('\n'));
  }
});
