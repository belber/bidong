const shareTitle = '壁咚咚 · B站视频收藏下载';
const sharePath = '/pages/home/home';

const pageShare = {
  onShareAppMessage() {
    return {
      title: shareTitle,
      path: sharePath
    };
  },

  onShareTimeline() {
    return {
      title: shareTitle,
      query: ''
    };
  }
};

module.exports = { pageShare, shareTitle, sharePath };
