// 校验激活码：非空且长度 ≥ 4，返回去除首尾空格后的值。
function validateActivationCode(input) {
  const code = String(input || '').trim();
  if (!code) {
    return { valid: false, code: '' };
  }
  if (code.length < 4) {
    return { valid: false, code };
  }
  return { valid: true, code };
}

module.exports = { validateActivationCode };
