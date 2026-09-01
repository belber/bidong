const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');

function toast(title) {
  wx.showToast({ title: title, icon: 'none' });
}

function sanitizeName(name) {
  const cleaned = (name || '').replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim();
  return (cleaned || 'bilibili').slice(0, 60);
}

function mediaFilename(title, bvid, kind) {
  const suffix = kind === 'audio' ? '.m4a' : '.mp4';
  return sanitizeName(title || bvid) + suffix;
}

function saveToAlbum(saveFn, filePath) {
  saveFn({
    filePath,
    success() { toast('已保存到相册'); },
    fail() {
      wx.showModal({
        title: '保存失败',
        content: '需要在设置中允许保存到相册',
        confirmText: '去设置',
        success(res) {
          if (res.confirm) { wx.openSetting(); }
        }
      });
    }
  });
}

Page({
  data: {
    cardId: 0,
    bvid: '',
    sourceUrl: '',
    title: '',
    upName: '',
    pubText: '',
    tags: [],
    desc: '',
    stats: { like: 0, reply: 0, favorite: 0, coin: 0 },
    coverUrl: '',
    media: { watermarked: false, clean: false, audio: false },
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0
  },

  onLoad() {
    const r = getApp().globalData.pendingResult || wx.getStorageSync('pending_result');
    if (!r) {
      toast('暂无解析数据');
      return;
    }
    const subtitles = (r.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));
    this.setData({
      cardId: r.id,
      bvid: r.bvid,
      sourceUrl: r.source_url,
      title: r.title,
      upName: r.up_name,
      pubText: formatDateTime(r.pubdate),
      tags: r.tags || [],
      desc: r.desc,
      stats: r.stats || { like: 0, reply: 0, favorite: 0, coin: 0 },
      coverUrl: r.cover_url,
      media: r.media || { watermarked: false, clean: false, audio: false },
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5)
    });
  },

  copy(field) {
    const v = this.data[field];
    if (!v) {
      toast('没有可复制的内容');
      return;
    }
    const text = Array.isArray(v) ? v.map((t) => '#' + t).join(' ') : String(v);
    wx.setClipboardData({ data: text, success() { toast('已复制'); } });
  },

  onCopyTag(e) {
    this.copy(e.currentTarget.dataset.field);
  },

  onPreviewCover() {
    if (this.data.coverUrl) {
      wx.previewImage({ urls: [this.data.coverUrl] });
    }
  },

  onSaveCover() {
    const url = this.data.coverUrl;
    if (!url) { return; }
    wx.downloadFile({
      url,
      success(res) {
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        saveToAlbum(wx.saveImageToPhotosAlbum, res.tempFilePath);
      },
      fail() { toast('下载失败'); }
    });
  },

  saveMedia(url, header, kind) {
    const filename = mediaFilename(this.data.title, this.data.bvid, kind);
    wx.downloadFile({
      url,
      header,
      success(res) {
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        if (kind === 'audio') {
          wx.shareFileMessage({ filePath: res.tempFilePath, fileName: filename });
        } else {
          saveToAlbum(wx.saveVideoToPhotosAlbum, res.tempFilePath);
        }
      },
      fail() { toast('下载失败'); }
    });
  },

  onDownloadVideo(e) {
    const kind = e.currentTarget.dataset.kind;
    api.mediaOptions(this.data.cardId, kind).then((options) => {
      if (!options.length) {
        toast('无可用清晰度');
        return;
      }
      wx.showActionSheet({
        itemList: options.map((o) => o.label),
        success: (res) => {
          const chosen = options[res.tapIndex];
          api.download(this.data.cardId, kind, chosen.qn).then(({ url, header }) => {
            this.saveMedia(url, header, kind);
          }).catch(() => toast('下载失败'));
        }
      });
    }).catch(() => toast('获取清晰度失败'));
  },

  onDownloadAudio() {
    api.download(this.data.cardId, 'audio').then(({ url, header }) => {
      this.saveMedia(url, header, 'audio');
    }).catch(() => toast('下载失败'));
  },

  onExport() {
    api.exportFile(this.data.cardId, 'txt').then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('导出失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('导出失败'); }
      });
    }).catch(() => toast('导出失败'));
  },

  onToggleSub() {
    this.setData({ showAllSub: !this.data.showAllSub });
  },

  onCopySub() {
    const lines = this.data.subtitles.map((s) => s.timeText + ' ' + s.text);
    if (!lines.length) { toast('无字幕'); return; }
    wx.setClipboardData({ data: lines.join('\n'), success() { toast('已复制'); } });
  },

  onDownloadSrt() {
    api.exportFile(this.data.cardId, 'srt').then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('导出失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('导出失败'); }
      });
    }).catch(() => toast('导出失败'));
  },

  onDownloadDanmaku() {
    api.danmaku(this.data.cardId).then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('下载失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('下载失败'); }
      });
    }).catch(() => toast('下载失败'));
  },

  onOpenBili() {
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      toast('B站小程序 appId 尚未配置');
      return;
    }
    wx.navigateToMiniProgram({ appId, path: '/pages/video/video?bvid=' + this.data.bvid });
  }
});
