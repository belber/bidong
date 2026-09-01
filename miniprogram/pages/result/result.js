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

function textFilename(title, bvid, suffix) {
  return sanitizeName(title || bvid) + suffix;
}

function copyToNamed(tempFilePath, filename) {
  return new Promise((resolve, reject) => {
    const dest = wx.env.USER_DATA_PATH + '/' + filename;
    const fs = wx.getFileSystemManager();
    try { fs.unlinkSync(dest); } catch (e) { /* 保留：目录不存在或文件不存在 */ }
    fs.copyFile({
      srcPath: tempFilePath,
      destPath: dest,
      success: () => resolve(dest),
      fail: reject
    });
  });
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

function shareNamedFile(tempFilePath, filename) {
  if (!wx.shareFileMessage) {
    toast('当前微信版本不支持文件分享');
    return;
  }
  const doShare = (filePath) => {
    wx.shareFileMessage({
      filePath,
      fileName: filename,
      fail(err) { toast((err && err.errMsg) || '分享失败'); }
    });
  };
  copyToNamed(tempFilePath, filename).then(doShare).catch(() => doShare(tempFilePath));
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
    tagsText: '',
    desc: '',
    stats: { like: 0, reply: 0, favorite: 0, coin: 0 },
    coverUrl: '',
    media: { watermarked: false, clean: false, audio: false },
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0,
    previewing: false
  },

  onLoad(options) {
    const bvid = (options && options.bvid) || '';
    if (bvid) {
      this.loadByBvid(bvid);
      return;
    }
    this.applyResult(getApp().globalData.pendingResult || wx.getStorageSync('pending_result'));
  },

  loadByBvid(bvid) {
    wx.showLoading({ title: '加载中' });
    api.parse('https://www.bilibili.com/video/' + bvid)
      .then((card) => {
        wx.hideLoading();
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        this.applyResult(card);
      })
      .catch((err) => {
        wx.hideLoading();
        toast(err.message || '加载失败');
      });
  },

  applyResult(r) {
    if (!r) {
      toast('暂无解析数据');
      return;
    }
    const subtitles = (r.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));
    const tags = Array.isArray(r.tags) ? r.tags : [];
    this.setData({
      cardId: r.id,
      bvid: r.bvid,
      sourceUrl: r.source_url,
      title: r.title,
      upName: r.up_name,
      pubText: formatDateTime(r.pubdate),
      tags,
      tagsText: tags.join(' '),
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
    if (!v || (Array.isArray(v) && !v.length)) {
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
      this.setData({ previewing: true });
    }
  },

  onClosePreview() {
    this.setData({ previewing: false });
  },

  onSaveCover() {
    const url = this.data.coverUrl;
    if (!url) { return; }
    wx.showLoading({ title: '下载中' });
    wx.downloadFile({
      url,
      success(res) {
        wx.hideLoading();
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        saveToAlbum(wx.saveImageToPhotosAlbum, res.tempFilePath);
      },
      fail() { wx.hideLoading(); toast('下载失败'); }
    });
  },

  saveMedia(url, header, kind) {
    const filename = mediaFilename(this.data.title, this.data.bvid, kind);
    wx.showLoading({ title: kind === 'audio' ? '准备分享' : '下载中' });
    wx.downloadFile({
      url,
      header,
      success(res) {
        wx.hideLoading();
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        if (kind === 'audio') {
          if (!wx.shareFileMessage) {
            toast('当前微信版本不支持文件分享');
            return;
          }
          wx.shareFileMessage({
            filePath: res.tempFilePath,
            fileName: filename,
            fail(err) { toast((err && err.errMsg) || '分享失败'); }
          });
        } else {
          saveToAlbum(wx.saveVideoToPhotosAlbum, res.tempFilePath);
        }
      },
      fail() { wx.hideLoading(); toast('下载失败'); }
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

  onToggleSub() {
    this.setData({ showAllSub: !this.data.showAllSub });
  },

  onCopySub() {
    const lines = this.data.subtitles.map((s) => s.timeText + ' ' + s.text);
    if (!lines.length) { toast('无字幕'); return; }
    wx.setClipboardData({ data: lines.join('\n'), success() { toast('已复制'); } });
  },

  onDownloadSrt() {
    wx.showLoading({ title: '导出中' });
    api.exportFile(this.data.cardId, 'srt').then(({ url, header }) => {
      const title = this.data.title;
      const bvid = this.data.bvid;
      wx.downloadFile({
        url,
        header,
        success(res) {
          wx.hideLoading();
          if (res.statusCode !== 200) { toast('导出失败'); return; }
          shareNamedFile(res.tempFilePath, textFilename(title, bvid, '.srt'));
        },
        fail() { wx.hideLoading(); toast('导出失败'); }
      });
    }).catch(() => { wx.hideLoading(); toast('导出失败'); });
  },

  onDownloadDanmaku() {
    wx.showLoading({ title: '下载中' });
    api.danmaku(this.data.cardId).then(({ url, header }) => {
      const title = this.data.title;
      const bvid = this.data.bvid;
      wx.downloadFile({
        url,
        header,
        success(res) {
          wx.hideLoading();
          if (res.statusCode !== 200) { toast('下载失败'); return; }
          shareNamedFile(res.tempFilePath, textFilename(title, bvid, '_弹幕.txt'));
        },
        fail() { wx.hideLoading(); toast('下载失败'); }
      });
    }).catch(() => { wx.hideLoading(); toast('下载失败'); });
  },

  onOpenBili() {
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      toast('B站小程序 appId 尚未配置');
      return;
    }
    wx.navigateToMiniProgram({ appId, path: '/pages/video/video?bvid=' + this.data.bvid });
  },

  onShareAppMessage() {
    return {
      title: this.data.title || 'B站视频收藏',
      path: '/pages/result/result?bvid=' + this.data.bvid,
      imageUrl: this.data.coverUrl
    };
  }
});
