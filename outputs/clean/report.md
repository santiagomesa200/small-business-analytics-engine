# Bluebonnet Supply Co. – Analysis report

Synthetic data. Every figure traces to a source file; missing or inconsistent figures are flagged, never estimated.

figures read: 95 | need attention: 0 | analyses fully computed: 5 of 5 (0 partial, 0 blocked) | verifier: PASS

## Executive summary

Gross margin went from 42.0% to 40.0% over the period, a change of -2.0 pp [gross_margin]. Revenue changed by $87,325 between the first and second half of the period: price contributed $24,125 and volume contributed $63,200 [price_volume]. Customers take about 44.8 days to pay, suppliers are paid in about 54.4 days, inventory sits for about 94.4 days and the cash conversion cycle is 84.8 days [working_capital]. Cash fell from $586,000 to $412,300, burning about $57,900 a month, which leaves about 7.1 months of runway at that pace [cash_runway]. At 4.0x to 6.0x annualized EBITDA of $199,814, equity value is $1,061,556 to $1,461,184 [valuation].

Drafted by: template. Checked by a separate verifier before it appears here.

## Needs attention (0 items)

- Nothing flagged.

## 1. Gross margin trend (computed)

| Item | Value | Source |
|---|---|---|
| Gross margin, January | 42.0% | pnl_2025_h1.xlsx \| Monthly P&L: B6, B4 |
| Gross margin, February | 41.5% | pnl_2025_h1.xlsx \| Monthly P&L: C6, C4 |
| Gross margin, March | 41.0% | pnl_2025_h1.xlsx \| Monthly P&L: D6, D4 |
| Gross margin, April | 41.0% | pnl_2025_h1.xlsx \| Monthly P&L: E6, E4 |
| Gross margin, May | 40.5% | pnl_2025_h1.xlsx \| Monthly P&L: F6, F4 |
| Gross margin, June | 40.0% | pnl_2025_h1.xlsx \| Monthly P&L: G6, G4 |
| Change, first to last month | -2.0 pp | pnl_2025_h1.xlsx \| Monthly P&L: B6, C6, D6, E6 +8 more |

Assumptions

- Gross margin = gross profit / revenue, per month.

## 2. Price vs volume effect on revenue (computed)

| Item | Value | Source |
|---|---|---|
| Revenue, base period | $1,089,850 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Revenue, current period | $1,177,175 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Total change | $87,325 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Price effect | $24,125 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Volume effect | $63,200 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Price effect: Conduit Kit | $25,625 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Volume effect: Conduit Kit | $23,100 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Price effect: Cable Spool | $7,800 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Volume effect: Cable Spool | $30,600 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Price effect: Safety Gear | -$9,300 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| Volume effect: Safety Gear | $9,500 | sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |

Assumptions

- Base period 2025-01 to 2025-03; current period 2025-04 to 2025-06.
- Price effect = change in average price x current units. Volume effect = change in units x base price. Product mix shows up inside the volume effect.
- Revenue here is units x price from the sales file, not the P&L.

## 3. Working capital (DSO, DPO, DIO) (computed)

| Item | Value | Source |
|---|---|---|
| DSO | 44.8 days | balance_sheet_2025-06-30.csv \| table: B3; sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| DPO | 54.4 days | balance_sheet_2025-06-30.csv \| table: B8; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +2 more |
| DIO | 94.4 days | balance_sheet_2025-06-30.csv \| table: B4; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +2 more |
| Cash conversion cycle | 84.8 days | balance_sheet_2025-06-30.csv \| table: B8, B3, B4; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +2 more; sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |

Assumptions

- DSO = receivables / revenue x days in the sales period. DPO = payables / COGS x days. DIO = inventory / COGS x days. Balance sheet figures are at period end.
- Cash conversion cycle = DSO + DIO - DPO.

## 4. Cash runway (computed)

| Item | Value | Source |
|---|---|---|
| Opening cash | $586,000 | bank_statement_summary.pdf \| page 1: line 6, line 2, line 3 |
| Ending cash | $412,300 | bank_statement_summary.pdf \| page 1: line 6, line 2, line 3 |
| Average monthly net burn | $57,900 | bank_statement_summary.pdf \| page 1: line 6, line 2, line 3 |
| Runway | 7.1 months | bank_statement_summary.pdf \| page 1: line 6, line 2, line 3 |

Assumptions

- Burn = (opening - ending cash) / months in the statement. It is assumed to continue unchanged.

## 5. Valuation range from an EBITDA multiple (computed)

| Item | Value | Source |
|---|---|---|
| Annualized EBITDA | $199,814 | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Multiple (low) | 4.0x | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Multiple (high) | 6.0x | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Net debt | -$262,300 | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Equity value (low) | $1,061,556 | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Equity value (mid) | $1,261,370 | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |
| Equity value (high) | $1,461,184 | bank_statement_summary.pdf \| page 1: line 7; balance_sheet_2025-06-30.csv \| table: B2; pnl_2025_h1.xlsx \| Monthly P&L: B8, C8, D8, E8 +2 more |

Assumptions

- EBITDA multiples of 4.0x, 5.0x and 6.0x are illustrative assumptions, not market comparables.
- Annualized EBITDA = the 6 months in the P&L scaled to 12 months. Seasonality is not adjusted.
- Net debt = line of credit (bank statement PDF) minus cash (balance sheet). Equity = multiple x EBITDA - net debt.

Provenance for every figure (file, sheet, cell, and the reason for any gap): figures.csv.
