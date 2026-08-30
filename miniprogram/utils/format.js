function pad(n) {
  return n < 10 ? '0' + n : '' + n;
}

// 秒数 → 'MM:SS'（超过 1 小时 → 'HH:MM:SS'）
function formatDuration(seconds) {
  const s = Number(seconds);
  if (!isFinite(s) || s < 0) {
    return '00:00';
  }
  const sec = Math.floor(s % 60);
  const min = Math.floor((s / 60) % 60);
  const hr = Math.floor(s / 3600);
  if (hr > 0) {
    return pad(hr) + ':' + pad(min) + ':' + pad(sec);
  }
  return pad(min) + ':' + pad(sec);
}

// unix 秒 → 'YYYY-MM'
function formatMonth(ts) {
  const d = new Date(ts * 1000);
  return d.getFullYear() + '-' + pad(d.getMonth() + 1);
}

// unix 秒 → 'YYYY-MM-DD HH:mm'
function formatDateTime(ts) {
  const d = new Date(ts * 1000);
  return (
    d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  );
}

module.exports = { formatDuration, formatMonth, formatDateTime };
