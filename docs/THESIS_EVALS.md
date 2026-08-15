# Thesis Evals

这些是小型、可重复的确定性评估，不是模型 benchmark。它们回答的是 Chronicle 的长期多主体命题是否仍然成立；真实 Hermes 和真人接受度另行记录。

| 命题 | 当前检查 | 证据边界 |
| --- | --- | --- |
| Session Reset | `tests/test_phase7_logical_moment.py::test_pending_moment_retries_after_executor_restart_before_commit`、`test_pending_moment_retry_after_commit_before_ack` | 验证 Host/Worldline restart 后的语义恢复，不声称模型 token 连续 |
| Subjective Memory Ablation | `tests/test_phase8_subject_continuity.py::test_memory_ablation_paired_fixture_changes_bounded_future_action` | 同一当前状态下，保留/移除主体记忆会改变受控 policy；不是模型大样本统计 |
| Cold Profile | [`receipts/ablation-attempt-6.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/ablation-attempt-6.md)：真实 Hermes warm/cold 对照；warm `wu-sangui` 保留 Experience，cold `wu-sangui-cold` 的 `MEMORY.md` 为空；相同只读 prompt、两个 fresh Session 均返回 200 | `memory_available=true` 的 warm 结果准确复述 implication，cold 返回 `false` 且不虚构；两边 Memory hash 前后不变。该 receipt 是一对受控 Profile 对照，不是统计学 benchmark |
| Profile Isolation / Merge Control | `tests/test_phase8_subject_continuity.py::test_single_agent_impostor_cannot_merge_private_lifetime_context`、`tests/test_v6_adversarial.py::test_single_agent_impostor_baseline_converges_while_peer_contexts_diverge` | 验证三个主体的私有视角不互相泄漏；不需要产品化合并 Profile |
| Epistemic Leakage | `tests/test_v6_context.py::test_reality_first_context_keeps_background_contrary_fact`、`tests/test_phase8_subject_continuity.py::test_later_action_trace_reuses_expectation_and_selective_memory` | 验证显式上下文/可见证据边界；不能消除模型参数中的历史先验 |
| Semantic Resume Equivalence | [`receipts/restart-attempt-6.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/restart-attempt-6.md)：确定性 restart/幂等测试，加上 live `worldline-c56e225d01824692` 完成 tick 5 后的真实 Chronicle kill/restart 前后 read-back | 比较持久化 Course、Experience、wake/causal refs 和世界状态；不要求自然语言逐字相同。receipt 证明状态恢复，不宣称新 Provider Wake 成功；一次 tick 0 重启后的 provider Wake 失败被 fail-closed，成功的 uninterrupted closure 与进程重启状态分开记录 |

当前最小新增能力由 Killer Demo 测试直接固定：Experience 只从已提交的承诺修订或主体行动后果产生；写入 Lifetime/Memory；后续判断可以显式引用它；公共 World 不得到这条私有经历。

运行全部确定性评估：

```bash
uv run pytest -q
```

旧南京、多危机和 V7 南北分支测试已显式标记为历史 skip；它们不属于当前单一山海关 V1 契约，也不应被解释为当前产品失败或当前能力证明。
