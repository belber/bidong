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
  const authorHandle = (origin.author_handle || '').trim();
  return {
    accountName: (origin.account_name || '').trim() || '帅哥录屏',
    accountAvatarUrl: origin.account_avatar_url || '',
    platformText: platformLabel || '—',
    authorText: authorName ? '@' + authorName : (platformLabel ? '待补充' : '—'),
    hasAuthor: !!authorName,
    // 复制按钮用的值：优先抖音号这类唯一账号标识（昵称会改，改了可能搜不到或搜错人），
    // 没有就退回昵称。主页链接在手机上粘不进去（抖音 App 搜索框不认 URL）。
    copyText: authorHandle || authorName,
    copyKind: authorHandle ? 'handle' : (authorName ? 'name' : ''),
    pending: !platformLabel && !authorName
  };
}

module.exports = { mapOrigin };
