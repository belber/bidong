const { validateActivationCode } = require('../miniprogram/utils/bind.js');

describe('validateActivationCode', () => {
  test('合法激活码通过并去除首尾空格', () => {
    expect(validateActivationCode('  ABC123  ')).toEqual({ valid: true, code: 'ABC123' });
  });

  test('空或纯空白无效', () => {
    expect(validateActivationCode('').valid).toBe(false);
    expect(validateActivationCode('   ').valid).toBe(false);
  });

  test('过短无效', () => {
    expect(validateActivationCode('ab').valid).toBe(false);
  });
});
