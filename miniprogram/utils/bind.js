// 从粘贴文本里提取激活码：优先取「激活码」标签后的字母数字串，
// 没有标签时取文本里的字母数字串，最后统一转大写。
function normalizeActivationCode(input) {
  const text = String(input || '').trim();
  if (!text) {
    return '';
  }
  const afterLabel = text.split(/激活码/i).pop() || text;
  const m = afterLabel.match(/[A-Za-z0-9]{4,}/);
  return (m ? m[0] : text).toUpperCase();
}

// 校验激活码：非空且长度 ≥ 4，返回标准化后的值。
function validateActivationCode(input) {
  const code = normalizeActivationCode(input);
  if (!code) {
    return { valid: false, code: '' };
  }
  if (code.length < 4) {
    return { valid: false, code };
  }
  return { valid: true, code };
}

module.exports = { validateActivationCode, normalizeActivationCode };
