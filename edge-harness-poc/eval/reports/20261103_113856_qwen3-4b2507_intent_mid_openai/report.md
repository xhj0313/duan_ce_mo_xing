# Intent 评测报告

- n=176  accuracy=0.9091  macro_F1=0.8914
- OOS 拒识率=0.9615384615384616  误拒率=0.0
- 最差召回类：rate_consult

| intent | P | R | F1 | support |
|---|---|---|---|---|
| rate_consult | 1.000 | 0.200 | 0.333 | 5 |
| card_apply | 0.667 | 0.400 | 0.500 | 5 |
| complaint_feedback | 1.000 | 0.600 | 0.750 | 5 |
| wealth_purchase | 1.000 | 0.600 | 0.750 | 5 |
| account_open | 0.571 | 0.800 | 0.667 | 5 |
| loan_apply | 1.000 | 0.800 | 0.889 | 5 |
| loss_report_guide | 1.000 | 0.800 | 0.889 | 5 |
| sms_notice_guide | 1.000 | 0.800 | 0.889 | 5 |
| out_of_scope | 1.000 | 0.962 | 0.980 | 26 |
| app_usage_guide | 1.000 | 1.000 | 1.000 | 5 |
| branch_hours | 1.000 | 1.000 | 1.000 | 5 |
| calc_deposit_interest | 0.714 | 1.000 | 0.833 | 5 |
| complex_consult | 0.714 | 1.000 | 0.833 | 5 |
| deposit_product_intro | 0.714 | 1.000 | 0.833 | 5 |
| exchange_rate_consult | 1.000 | 1.000 | 1.000 | 5 |
| fee_consult | 0.714 | 1.000 | 0.833 | 5 |
| find_branch | 1.000 | 1.000 | 1.000 | 5 |
| loan_condition_consult | 0.833 | 1.000 | 0.909 | 5 |
| loss_report_execute | 0.833 | 1.000 | 0.909 | 5 |
| password_change_execute | 1.000 | 1.000 | 1.000 | 5 |
| password_reset_guide | 1.000 | 1.000 | 1.000 | 5 |
| query_balance | 1.000 | 1.000 | 1.000 | 5 |
| query_deposit_holding | 1.000 | 1.000 | 1.000 | 5 |
| query_quota_value | 1.000 | 1.000 | 1.000 | 5 |
| query_recent_transactions | 1.000 | 1.000 | 1.000 | 5 |
| quota_consult | 1.000 | 1.000 | 1.000 | 5 |
| security_tips | 1.000 | 1.000 | 1.000 | 5 |
| service_channel_consult | 1.000 | 1.000 | 1.000 | 5 |
| statement_consult | 1.000 | 1.000 | 1.000 | 5 |
| transfer_out | 1.000 | 1.000 | 1.000 | 5 |
| wealth_product_intro | 0.714 | 1.000 | 0.833 | 5 |

阈值判定：{"macro_f1>=0.90": false, "oos_reject>=0.85": true, "min_class_recall>=0.85": false}
