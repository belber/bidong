Page(Object.assign({
  data: {
    groupNo: '',
    showGroup: false,
    showRobotGuide: false,
    robotExpanded: false,
    expandedFaq: '',
    faqs: [
      {id: 'files', title: '下载的文件保存在哪里？', answer: '视频下载后点击「保存」，存入手机相册。音频、字幕、评论等文件下载后点击「保存」，选择微信聊天发送；文案 TXT 下载后点击「转发到微信」。'},
      {id: 'transcript', title: '怎么提取和导出文案？', answer: '解析后点击「提取文案」，完成后点「查看文案」，可切换时间轴与纯文本、复制全文或导出TXT。只解析或下载不会自动提取；图文作品不支持。'},
      {id: 'summary', title: '怎么用元宝总结？', answer: '在文案页点「去元宝总结」，文案与指令会自动复制，确认前往元宝后粘贴发送即可。总结由元宝提供；若粘贴长度受限，可分段粘贴。'},
      {id: 'failure', title: '下载或提取失败怎么办？', answer: '先检查网络，再按页面提示重试；保存相册失败时检查微信相册权限。提取中可稍后回来，无语音通常表示只有音乐或人声不清；识别文字请核对后使用。'},
      {id: 'more', title: '封面和原字幕在哪里？', answer: '展开解析页「更多信息」，点击封面预览，长按可保存。有平台原字幕时才显示字幕，可复制或下载；不会用识别文案替代，评论与弹幕以页面实际提供为准。'},
      {id: 'collection', title: '怎么整理或删除收藏？', answer: '解析成功后视频会自动收藏，在「收藏夹」可搜索、按标签和月份查找。进入多选后选择卡片，可整理标签或删除收藏。'}
    ]
  },

  onLoad() {
    const api = require('../../utils/api');
    const group = api
      .getHelpConfig()
      .then((cfg) => {
        const no = ((cfg && cfg.qq_group) || '').trim();
        this.setData({ groupNo: no, showGroup: !!no });
      })
      .catch(() => this.setData({ showGroup: false }));
    const robot = api.getPublicConfig()
      .then(cfg => this.setData({showRobotGuide: !!cfg && cfg.robot_guide !== false}))
      .catch(() => this.setData({showRobotGuide: false}));
    return Promise.all([group, robot]);
  },

  onToggleFaq(e) {
    const id = e.currentTarget.dataset.id;
    if (!this.data.faqs.some(item => item.id === id)) return;
    this.setData({expandedFaq: this.data.expandedFaq === id ? '' : id});
  },

  onToggleRobot() {
    this.setData({robotExpanded: !this.data.robotExpanded});
  },

  onCopyGroup() {
    if (!this.data.groupNo) return;
    wx.setClipboardData({
      data: this.data.groupNo,
      success: () => wx.showToast({ title: '群号已复制，去 QQ 搜索加入', icon: 'none' }),
      fail: () => wx.showToast({title: '复制失败，请重试', icon: 'none'})
    });
  }
}, require("../../utils/share.js").pageShare));
