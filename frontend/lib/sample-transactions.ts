/**
 * Sample transactions for the onboarding "Add sample transactions" button.
 * These create enough data for recurring detection and forecast computation.
 */
export const SAMPLE_TRANSACTIONS = [
  { raw_description: "PAYROLL EMPLOYER INC", amount: 2500.0, transaction_type: "credit", days_ago: 1 },
  { raw_description: "RENT PAYMENT FEB", amount: 1100.0, transaction_type: "debit", days_ago: 1 },
  { raw_description: "GROCERY MART", amount: 85.5, transaction_type: "debit", days_ago: 2 },
  { raw_description: "NETFLIX.COM", amount: 15.99, transaction_type: "debit", days_ago: 3 },
  { raw_description: "SPOTIFY USA", amount: 11.99, transaction_type: "debit", days_ago: 3 },
  { raw_description: "GAS STATION", amount: 45.0, transaction_type: "debit", days_ago: 4 },
  { raw_description: "PHARMACY CVS", amount: 22.0, transaction_type: "debit", days_ago: 5 },
  { raw_description: "COFFEE SHOP", amount: 5.5, transaction_type: "debit", days_ago: 5 },
  { raw_description: "ELECTRIC COMPANY", amount: 95.0, transaction_type: "debit", days_ago: 6 },
  { raw_description: "CELL PHONE BILL", amount: 65.0, transaction_type: "debit", days_ago: 7 },
];

export function buildTransactionPayload(accountId: string) {
  return SAMPLE_TRANSACTIONS.map((t) => {
    const d = new Date();
    d.setDate(d.getDate() - t.days_ago);
    return {
      account_id: accountId,
      raw_description: t.raw_description,
      amount: t.amount,
      transaction_type: t.transaction_type,
      transaction_date: d.toISOString(),
      currency: "USD",
    };
  });
}
