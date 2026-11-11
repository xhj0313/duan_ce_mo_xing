# Intent 评测报告

- n=100  accuracy=0.1500  macro_F1=0.0878
- OOS 拒识率=None  误拒率=0.0
- 最差召回类：app_usage_guide

| intent | P | R | F1 | support |
|---|---|---|---|---|
| app_usage_guide | 0.000 | 0.000 | 0.000 | 5 |
| branch_hours | 0.000 | 0.000 | 0.000 | 5 |
| calc_deposit_interest | 0.000 | 0.000 | 0.000 | 0 |
| deposit_product_intro | 0.000 | 0.000 | 0.000 | 5 |
| exchange_rate_consult | 0.000 | 0.000 | 0.000 | 5 |
| loan_condition_consult | 0.000 | 0.000 | 0.000 | 5 |
| loss_report_guide | 0.000 | 0.000 | 0.000 | 5 |
| password_reset_guide | 0.000 | 0.000 | 0.000 | 5 |
| query_deposit_holding | 0.000 | 0.000 | 0.000 | 5 |
| query_quota_value | 0.000 | 0.000 | 0.000 | 5 |
| query_recent_transactions | 0.000 | 0.000 | 0.000 | 5 |
| quota_consult | 0.000 | 0.000 | 0.000 | 5 |
| rate_consult | 0.000 | 0.000 | 0.000 | 5 |
| security_tips | 0.000 | 0.000 | 0.000 | 5 |
| service_channel_consult | 0.000 | 0.000 | 0.000 | 5 |
| sms_notice_guide | 0.000 | 0.000 | 0.000 | 5 |
| statement_consult | 0.000 | 0.000 | 0.000 | 5 |
| transfer_out | 0.000 | 0.000 | 0.000 | 0 |
| wealth_product_intro | 0.000 | 0.000 | 0.000 | 5 |
| fee_consult | 0.833 | 1.000 | 0.909 | 5 |
| find_branch | 0.833 | 1.000 | 0.909 | 5 |
| query_balance | 0.060 | 1.000 | 0.112 | 5 |

阈值判定：{"macro_f1>=0.90": false, "oos_reject>=0.85": false, "min_class_recall>=0.85": false}
