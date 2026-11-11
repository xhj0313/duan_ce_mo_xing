# Intent 评测报告

- n=50  accuracy=0.7400  macro_F1=0.5766
- OOS 拒识率=None  误拒率=0.08
- 最差召回类：rate_consult

| intent | P | R | F1 | support |
|---|---|---|---|---|
| calc_deposit_interest | 0.000 | 0.000 | 0.000 | 0 |
| loss_report_execute | 0.000 | 0.000 | 0.000 | 0 |
| out_of_scope | 0.000 | 0.000 | 0.000 | 0 |
| quota_consult | 0.000 | 0.000 | 0.000 | 0 |
| rate_consult | 1.000 | 0.200 | 0.333 | 5 |
| deposit_product_intro | 1.000 | 0.600 | 0.750 | 5 |
| exchange_rate_consult | 1.000 | 0.600 | 0.750 | 5 |
| loss_report_guide | 1.000 | 0.600 | 0.750 | 5 |
| wealth_product_intro | 0.600 | 0.600 | 0.600 | 5 |
| fee_consult | 1.000 | 0.800 | 0.889 | 5 |
| app_usage_guide | 1.000 | 1.000 | 1.000 | 5 |
| branch_hours | 1.000 | 1.000 | 1.000 | 5 |
| loan_condition_consult | 1.000 | 1.000 | 1.000 | 5 |
| password_reset_guide | 1.000 | 1.000 | 1.000 | 5 |

阈值判定：{"macro_f1>=0.90": false, "oos_reject>=0.85": false, "min_class_recall>=0.85": false}
