# Bluebonnet Supply Co. – Analysis report

Synthetic data. Every figure traces to a source file; missing or inconsistent figures are flagged, never estimated.

figures read: 95 | need attention: 2 | analyses fully computed: 2 of 5 (2 partial, 1 blocked) | verifier: PASS

## Executive summary

Gross margin was 42.0% in January and 40.0% in June; April and May are not computed because April's figures are missing and May's subtotal does not add up, so the change over the period is not computed either [gross_margin]. Revenue changed by $87,325 between the first and second half of the period: price contributed $24,125 and volume contributed $63,200 [price_volume]. Customers take about 44.8 days to pay; supplier payment days, inventory days and the cash conversion cycle are not computed because April's figures are missing [working_capital]. Cash fell from $586,000 to $412,300, burning about $57,900 a month, which leaves about 7.1 months of runway at that pace [cash_runway]. The valuation range from an EBITDA multiple is not computed because April's figures are missing, so no figures are stated for it; send the April column to unblock it [valuation].

Drafted by: template. Checked by a separate verifier before it appears here.

## Needs attention (2 items)

- April is missing from the Monthly P&L. This blocks: April gross margin, supplier payment days, inventory days, valuation range from an EBITDA multiple. Fix: send the April column.
  Technical detail: pnl.revenue.2025-04, pnl.cogs.2025-04, pnl.gross_profit.2025-04, pnl.opex.2025-04, pnl.ebitda.2025-04
- May's gross profit is $168,519 in the file, but its parts add up to $159,519. This blocks: May gross margin. Fix: confirm the right figure with whoever prepared the file.
  Technical detail: pnl.gross_profit.2025-05

## 1. Gross margin trend (partial)

| Item | Value | Source |
|---|---|---|
| Gross margin, January | 42.0% | pnl_2025_h1.xlsx \| Monthly P&L: B6, B4 |
| Gross margin, February | 41.5% | pnl_2025_h1.xlsx \| Monthly P&L: C6, C4 |
| Gross margin, March | 41.0% | pnl_2025_h1.xlsx \| Monthly P&L: D6, D4 |
| Gross margin, April | not computed (April's figures are missing) | pnl_2025_h1.xlsx \| Monthly P&L |
| Gross margin, May | not computed (May's subtotal does not add up) | pnl_2025_h1.xlsx \| Monthly P&L: E6, E4 |
| Gross margin, June | 40.0% | pnl_2025_h1.xlsx \| Monthly P&L: F6, F4 |
| Change, first to last month | not computed (a month in the range is flagged) | pnl_2025_h1.xlsx \| Monthly P&L: B6, C6, D6, E6 +6 more |

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

## 3. Working capital (DSO, DPO, DIO) (partial)

| Item | Value | Source |
|---|---|---|
| DSO | 44.8 days | balance_sheet_2025-06-30.csv \| table: B3; sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |
| DPO | not computed (April's figures are missing) | balance_sheet_2025-06-30.csv \| table: B8; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +1 more |
| DIO | not computed (April's figures are missing) | balance_sheet_2025-06-30.csv \| table: B4; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +1 more |
| Cash conversion cycle | not computed (one of the measures above is missing) | balance_sheet_2025-06-30.csv \| table: B8, B3, B4; pnl_2025_h1.xlsx \| Monthly P&L: B5, C5, D5, E5 +1 more; sales_by_product.csv \| table: D8, D9, D10, D11 +32 more |

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

## 5. Valuation range from an EBITDA multiple (blocked)

Not computed because April's figures are missing. Fix: send the April column.

Technical detail: not computed: missing pnl.ebitda.2025-04 (the 2025-04 column is absent from 'Monthly P&L')

Provenance for every figure (file, sheet, cell, and the reason for any gap): figures.csv.
