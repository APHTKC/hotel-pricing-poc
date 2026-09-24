export function numeric(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function average(values) {
  const valid = values.map(numeric).filter(Number.isFinite);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

export function median(values) {
  const valid = values.map(numeric).filter(Number.isFinite).sort((a, b) => a - b);
  if (!valid.length) return null;
  const middle = Math.floor(valid.length / 2);
  return valid.length % 2 ? valid[middle] : (valid[middle - 1] + valid[middle]) / 2;
}

export function roomSizeBand(value) {
  const size = numeric(value);
  if (size === null || size <= 0) return 'unknown';
  if (size < 45) return '<45㎡';
  if (size < 60) return '45–59㎡';
  if (size < 80) return '60–79㎡';
  return '80㎡+';
}

export function convertCurrency(value, currency, rates) {
  const number = numeric(value);
  return number === null ? null : number * (numeric(rates?.[currency]) || 1);
}

export function formatMoney(value, { locale = 'zh-TW', currency = 'TWD', rates = { TWD: 1 } } = {}) {
  const converted = convertCurrency(value, currency, rates);
  return converted === null ? '—' : new Intl.NumberFormat(locale, {
    style: 'currency', currency, maximumFractionDigits: 0,
  }).format(converted);
}
