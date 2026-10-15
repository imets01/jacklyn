import type { TransactionType } from "./types";

export const TYPE_LABELS: Record<TransactionType, string> = {
  buy: "Buy",
  sell: "Sell",
  dividend: "Dividend",
  interest: "Interest",
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  fee: "Fee",
  tax: "Tax",
  fx: "FX conversion",
  transfer_in: "Transfer in",
  transfer_out: "Transfer out",
};
