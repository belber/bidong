// 从用户粘贴/分享的文本中识别 B站链接。
// 返回：
//   { kind: 'video', bvid, url }         完整视频链接或纯 BV 号
//   { kind: 'short', url }               b23.tv 短链（交给后端解析）
//   null                                 不是 B站链接

const VIDEO_URL_RE = /(?:https?:\/\/)?(?:www\.|m\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10})(?:\/\S*)?/i;
const B23_RE = /https?:\/\/b23\.tv\/[0-9A-Za-z]+/i;
const BV_RE = /\bBV[0-9A-Za-z]{10}\b/;

// 抖音：
//   https://v.douyin.com/xxxx/           短链，交给后端跟随 302
//   https://www.douyin.com/video/<id>    视频作品页
//   https://www.douyin.com/note/<id>     图文作品页
//   https://www.iesdouyin.com/share/slides/<id>/  图文分享页（短链的终点）
const DY_SHORT_RE = /https?:\/\/v\.douyin\.com\/[0-9A-Za-z_-]+\/?/i;
const DY_SHARE_RE = /https?:\/\/[^\s]*douyin\.com\/(?:share\/)?(?:video|note|slides)\/\d+\/?/i;
const DY_PAGE_RE = /https?:\/\/[^\s]*douyin\.com\/(video|note)\/(\d{6,})/i;

function extractDouyinLink(text) {
  if (!text || !text.trim()) {
    return null;
  }

  const short = text.match(DY_SHORT_RE);
  if (short) {
    return { kind: 'short', url: short[0] };
  }

  const page = text.match(DY_PAGE_RE);
  if (page) {
    return {
      kind: page[1].toLowerCase(),
      awemeId: page[2],
      url: 'https://www.douyin.com/' + page[1].toLowerCase() + '/' + page[2]
    };
  }

  const share = text.match(DY_SHARE_RE);
  if (share) {
    return { kind: 'short', url: share[0] };
  }

  return null;
}

// 首页只有一个「贴链接」入口，统一在这里认平台。
function extractLink(text) {
  const douyin = extractDouyinLink(text);
  if (douyin) {
    return { platform: 'douyin', link: douyin };
  }
  const bili = extractBiliLink(text);
  if (bili) {
    return { platform: 'bilibili', link: bili };
  }
  return null;
}

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

module.exports = { extractBiliLink, extractDouyinLink, extractLink };
