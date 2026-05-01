import type { Currency } from '../types';

export const CURRENCIES: { code: Currency; label: string; symbol: string }[] = [
  { code: 'PKR', label: 'Pakistani Rupee', symbol: '₨' },
  { code: 'INR', label: 'Indian Rupee',    symbol: '₹' },
  { code: 'USD', label: 'US Dollar',       symbol: '$' },
  { code: 'EUR', label: 'Euro',            symbol: '€' },
  { code: 'GBP', label: 'British Pound',   symbol: '£' },
  { code: 'AED', label: 'UAE Dirham',      symbol: 'د.إ' },
  { code: 'SAR', label: 'Saudi Riyal',     symbol: '﷼' },
];

export function getCurrencySymbol(code: Currency): string {
  return CURRENCIES.find(c => c.code === code)?.symbol ?? code;
}

export function formatPrice(amount: number, currency: Currency): string {
  const symbol = getCurrencySymbol(currency);
  // PKR and INR typically show no decimal places
  const decimals = ['PKR', 'INR', 'SAR', 'AED'].includes(currency) ? 0 : 2;
  return `${symbol}${amount.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}
