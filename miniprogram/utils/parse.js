// 从用户粘贴/分享的文本中识别 B站链接。
// 返回：
//   { kind: 'video', bvid, url }         完整视频链接或纯 BV 号
//   { kind: 'short', url }               b23.tv 短链（交给后端解析）
//   null                                 不是 B站链接

const VIDEO_URL_RE = /(?:https?:\/\/)?(?:www\.|m\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10})(?:\/\S*)?/i;
const B23_RE = /https?:\/\/b23\.tv\/[0-9A-Za-z]+/i;
const BV_RE = /\bBV[0-9A-Za-z]{10}\b/;

function extractBiliLink(text) {
  if (!text || !text.trim()) {
    return null;
  }

  const video = text.match(VIDEO_URL_RE);
  if (video) {
    const bvid = video[1];
    return {
      kind: 'video',
      bvid,
      url: 'https://www.bilibili.com/video/' + bvid
    };
  }

  const short = text.match(B23_RE);
  if (short) {
    return { kind: 'short', url: short[0] };
  }

  const bv = text.match(BV_RE);
  if (bv) {
    const bvid = bv[0];
    return {
      kind: 'video',
      bvid,
      url: 'https://www.bilibili.com/video/' + bvid
    };
  }

  return null;
}

module.exports = { extractBiliLink };
