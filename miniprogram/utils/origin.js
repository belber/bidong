// 「帅哥录屏 · 原up主是谁」区块的视图模型。
// 后端只在白名单账号（帅哥录屏）的视频上返回 origin；查不到出处时字段为空，
// 由这里决定展示成占位符还是「待补充」。
function mapOrigin(origin) {
  if (!origin) {
    return null;
  }
  const platformLabel = (origin.platformLabel || '').trim();
  const authorName = (origin.authorName || '').trim();
  return {
    accountName: (origin.accountName || '').trim() || '帅哥录屏',
    accountAvatarUrl: origin.accountAvatarUrl || '',
    platformText: platformLabel || '—',
    authorText: authorName ? '@' + authorName : (platformLabel ? '待补充' : '—'),
    hasAuthor: !!authorName,
    authorUrl: origin.authorUrl || '',
    pending: !platformLabel && !authorName
  };
}

module.exports = { mapOrigin };
