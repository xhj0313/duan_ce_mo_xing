# Intent 评测报告

- n=168  accuracy=0.8155  macro_F1=0.8178
- OOS 拒识率=0.7692307692307693  误拒率=0.06338028169014084
- 最差召回类：rate_consult

| intent | P | R | F1 | support |
|---|---|---|---|---|
| rate_consult | 1.000 | 0.200 | 0.333 | 5 |
| statement_consult | 1.000 | 0.400 | 0.571 | 5 |
| complaint_feedback | 1.000 | 0.600 | 0.750 | 5 |
| deposit_product_intro | 1.000 | 0.600 | 0.750 | 5 |
| exchange_rate_consult | 1.000 | 0.600 | 0.750 | 5 |
| loss_report_guide | 1.000 | 0.600 | 0.750 | 5 |
| security_tips | 0.750 | 0.600 | 0.667 | 5 |
| wealth_product_intro | 0.600 | 0.600 | 0.600 | 5 |
| card_apply | 0.667 | 0.667 | 0.667 | 3 |
| wealth_purchase | 1.000 | 0.750 | 0.857 | 4 |
| out_of_scope | 0.690 | 0.769 | 0.727 | 26 |
| account_open | 0.800 | 0.800 | 0.800 | 5 |
| loss_report_execute | 0.667 | 0.800 | 0.727 | 5 |
| query_deposit_holding | 1.000 | 0.800 | 0.889 | 5 |
| quota_consult | 1.000 | 0.800 | 0.889 | 5 |
| app_usage_guide | 1.000 | 1.000 | 1.000 | 5 |
| branch_hours | 1.000 | 1.000 | 1.000 | 5 |
| calc_deposit_interest | 0.556 | 1.000 | 0.714 | 5 |
| complex_consult | 0.556 | 1.000 | 0.714 | 5 |
| fee_consult | 0.833 | 1.000 | 0.909 | 5 |
| find_branch | 0.833 | 1.000 | 0.909 | 5 |
| loan_condition_consult | 1.000 | 1.000 | 1.000 | 5 |
| password_change_execute | 1.000 | 1.000 | 1.000 | 5 |
| password_reset_guide | 1.000 | 1.000 | 1.000 | 5 |
| query_balance | 0.833 | 1.000 | 0.909 | 5 |
| query_quota_value | 1.000 | 1.000 | 1.000 | 5 |
| query_recent_transactions | 0.714 | 1.000 | 0.833 | 5 |
| service_channel_consult | 0.833 | 1.000 | 0.909 | 5 |
| sms_notice_guide | 1.000 | 1.000 | 1.000 | 5 |
| transfer_out | 0.833 | 1.000 | 0.909 | 5 |

阈值判定：{"macro_f1>=0.90": false, "oos_reject>=0.85": false, "min_class_recall>=0.85": false}
