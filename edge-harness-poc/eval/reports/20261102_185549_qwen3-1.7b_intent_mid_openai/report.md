# Intent 评测报告

- n=176  accuracy=0.8352  macro_F1=0.8104
- OOS 拒识率=0.6153846153846154  误拒率=0.006666666666666667
- 最差召回类：rate_consult

| intent | P | R | F1 | support |
|---|---|---|---|---|
| query_statement_consult | 0.000 | 0.000 | 0.000 | 0 |
| rate_consult | 1.000 | 0.200 | 0.333 | 5 |
| statement_consult | 1.000 | 0.200 | 0.333 | 5 |
| card_apply | 0.667 | 0.400 | 0.500 | 5 |
| wealth_purchase | 1.000 | 0.600 | 0.750 | 5 |
| out_of_scope | 0.941 | 0.615 | 0.744 | 26 |
| account_open | 0.500 | 0.800 | 0.615 | 5 |
| complaint_feedback | 1.000 | 0.800 | 0.889 | 5 |
| complex_consult | 0.667 | 0.800 | 0.727 | 5 |
| loan_condition_consult | 1.000 | 0.800 | 0.889 | 5 |
| loss_report_execute | 1.000 | 0.800 | 0.889 | 5 |
| password_change_execute | 1.000 | 0.800 | 0.889 | 5 |
| app_usage_guide | 0.833 | 1.000 | 0.909 | 5 |
| branch_hours | 1.000 | 1.000 | 1.000 | 5 |
| calc_deposit_interest | 0.556 | 1.000 | 0.714 | 5 |
| deposit_product_intro | 1.000 | 1.000 | 1.000 | 5 |
| exchange_rate_consult | 0.714 | 1.000 | 0.833 | 5 |
| fee_consult | 1.000 | 1.000 | 1.000 | 5 |
| find_branch | 0.625 | 1.000 | 0.769 | 5 |
| loan_apply | 1.000 | 1.000 | 1.000 | 5 |
| loss_report_guide | 1.000 | 1.000 | 1.000 | 5 |
| password_reset_guide | 0.833 | 1.000 | 0.909 | 5 |
| query_balance | 0.833 | 1.000 | 0.909 | 5 |
| query_deposit_holding | 1.000 | 1.000 | 1.000 | 5 |
| query_quota_value | 1.000 | 1.000 | 1.000 | 5 |
| query_recent_transactions | 0.714 | 1.000 | 0.833 | 5 |
| quota_consult | 0.833 | 1.000 | 0.909 | 5 |
| security_tips | 0.625 | 1.000 | 0.769 | 5 |
| service_channel_consult | 0.833 | 1.000 | 0.909 | 5 |
| sms_notice_guide | 1.000 | 1.000 | 1.000 | 5 |
| transfer_out | 1.000 | 1.000 | 1.000 | 5 |
| wealth_product_intro | 0.833 | 1.000 | 0.909 | 5 |

阈值判定：{"macro_f1>=0.90": false, "oos_reject>=0.85": false, "min_class_recall>=0.85": false}
