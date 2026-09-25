// 「帅哥录屏 · 原up主是谁」区块的视图模型。
// 后端只在白名单账号（帅哥录屏）的视频上返回 origin；查不到出处时字段为空，
// 由这里决定展示成占位符还是「待补充」。
// 注意：后端沿用 snake_case（和 cover_url / up_name 一致），这里做一次映射。
function mapOrigin(origin) {
  if (!origin) {
    return null;
  }
  const platformLabel = (origin.platform_label || '').trim();
  const authorName = (origin.author_name || '').trim();
  return {
    accountName: (origin.account_name || '').trim() || '帅哥录屏',
    accountAvatarUrl: origin.account_avatar_url || '',
    platformText: platformLabel || '—',
    authorText: authorName ? '@' + authorName : (platformLabel ? '待补充' : '—'),
    hasAuthor: !!authorName,
    authorUrl: origin.author_url || '',
    pending: !platformLabel && !authorName
  };
}

module.exports = { mapOrigin };
